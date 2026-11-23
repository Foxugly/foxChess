"""Ce que foxChess laisse partir vers Sentry.

foxChess ne connaît aucune donnée personnelle de ses joueurs (parties
anonymes, liées à la session). Restent la règle de la flotte (OPERATIONS.md
§3.25 : ni secret ni donnée personnelle chez Sentry) et le bruit : pas de
corps de requête, pas de variables locales, pas de cookies, pas de query
string, et pas d'erreur `DisallowedHost` (les robots qui appellent l'IP).
"""

from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import DisallowedHost
from sentry_sdk.scrubber import EventScrubber

#: Les seuls en-têtes de requête transmis.
ENTETES_PERMIS = frozenset({
    "accept",
    "accept-language",
    "content-length",
    "content-type",
    "host",
    "user-agent",
    "x-forwarded-proto",
})


def masquer_url(url):
    """URL sans query string ni fragment."""
    if not isinstance(url, str):
        return url
    morceaux = urlsplit(url)
    return urlunsplit((morceaux.scheme, morceaux.netloc, morceaux.path, "", ""))


# Termes proxy/IP que le SDK lui-même ajoute quand il traduit
# `send_default_pii=False` ; s'ajoutent à sa liste noire de clés sensibles.
_TERMES_PII = ["forwarded", "-ip", "remote-", "via", "-user"]

#: Ce que le SDK collecte de lui-même (sentry-sdk 2.76 : remplace
#: `send_default_pii=False`, devenu obsolète). Ni utilisateur, ni cookies, ni
#: corps de requête, ni variables locales, ni paramètres SQL : jamais plus qu'avant.
DONNEES_COLLECTEES = {
    "user_info": False,
    "cookies": {"mode": "off"},
    "http_headers": {"request": {"mode": "denylist", "terms": _TERMES_PII}},
    "http_bodies": [],
    "url_query_params": {"mode": "denylist", "terms": _TERMES_PII},
    "graphql": {"document": False, "variables": False},
    "gen_ai": {"inputs": False, "outputs": False},
    "database_query_data": False,
    "queues": False,
    "stack_frame_variables": False,
    "frame_context_lines": 5,
}

# Passer `data_collection` coupe l'EventScrubber du SDK : on le rejoue en tête
# de nos propres filtres (extra, fils d'Ariane, spans).
_SCRUBBER = EventScrubber(send_default_pii=False)


def _nettoyer(evenement):
    _SCRUBBER.scrub_event(evenement)
    requete = evenement.get("request")
    if isinstance(requete, dict):
        entetes = requete.get("headers") or {}
        evenement["request"] = {
            "method": requete.get("method"),
            "url": masquer_url(requete.get("url")),
            "headers": {
                nom: valeur for nom, valeur in entetes.items()
                if str(nom).lower() in ENTETES_PERMIS
            } if isinstance(entetes, dict) else {},
        }
    utilisateur = evenement.get("user")
    if isinstance(utilisateur, dict) and utilisateur.get("id") is not None:
        evenement["user"] = {"id": str(utilisateur["id"])}
    else:
        evenement.pop("user", None)
    return evenement


def avant_envoi(evenement, indice):
    """`before_send` : erreurs et messages."""
    erreur = (indice or {}).get("exc_info", (None, None))[1]
    if isinstance(erreur, DisallowedHost):
        return None
    return _nettoyer(evenement)


def avant_transaction(evenement, indice):
    """`before_send_transaction` : mesures de performance."""
    return _nettoyer(evenement)


def reglages_sentry():
    """Options de `sentry_sdk.init`, partagées par les réglages et les tests."""
    return {
        # Ni PII, ni cookies, ni corps, ni variables locales : `DONNEES_COLLECTEES`.
        "data_collection": DONNEES_COLLECTEES,
        "max_request_body_size": "never",
        "before_send": avant_envoi,
        "before_send_transaction": avant_transaction,
    }

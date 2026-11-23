"""Ce que foxChess laisse partir vers Sentry.

foxChess ne connaît aucune donnée personnelle de ses joueurs (parties
anonymes, liées à la session). Restent la règle de la flotte (OPERATIONS.md
§3.25 : ni secret ni donnée personnelle chez Sentry) et le bruit : pas de
corps de requête, pas de variables locales, pas de cookies, pas de query
string, et pas d'erreur `DisallowedHost` (les robots qui appellent l'IP).
"""

import logging
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import DisallowedHost
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from config.sentry_scrub import FILTERED, scrub_event, scrub_span

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

#: Ce que le SDK collecte de lui-même (sentry-sdk 3 : remplace
#: `send_default_pii=False`, supprimé). Ni utilisateur, ni cookies, ni
#: corps de requête, ni variables locales, ni paramètres SQL : jamais plus qu'avant.
DONNEES_COLLECTEES = {
    "user_info": False,
    "cookies": {"mode": "off"},
    "http_headers": {"request": {"mode": "denylist", "terms": _TERMES_PII}},
    "http_bodies": [],
    "url_query_params": {"mode": "denylist", "terms": _TERMES_PII},
    "graphql": {"document": False, "variables": False},
    "gen_ai": {"inputs": False, "outputs": False},
    "mcp": {"inputs": False, "outputs": False},
    "database_query_data": False,
    "queues": False,
    "stack_frame_variables": False,
    "frame_context_lines": 5,
}

def _nettoyer(evenement):
    # sentry-sdk 3 a supprimé son EventScrubber : `config/sentry_scrub` en
    # rejoue la liste noire (extra, fils d'Ariane, variables) avant nos filtres.
    scrub_event(evenement)
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


#: Attributs de span jamais transmis : query string, fragment, corps.
_ATTRIBUTS_RETIRES = frozenset({
    "url.query", "url.fragment", "http.query", "http.fragment", "http.request.body.data",
})
_PREFIXE_ENTETE = "http.request.header."


def _attribut_permis(cle):
    if cle in _ATTRIBUTS_RETIRES:
        return False
    if cle.startswith(_PREFIXE_ENTETE):
        return cle[len(_PREFIXE_ENTETE):].lower().replace("_", "-") in ENTETES_PERMIS
    return not cle.startswith("user.") or cle == "user.id"


def avant_span(span, indice):
    """`before_send_span` (sentry-sdk 3 : les spans remplacent les transactions).

    Liste noire du SDK sur le nom et les attributs (`scrub_span`), puis les
    mêmes règles que pour une erreur : URL sans query string, en-têtes de la
    liste blanche, utilisateur réduit à son identifiant. Ne lève jamais : une
    exception ferait partir le span d'origine.
    """
    span = scrub_span(span)
    try:
        attributs = span.get("attributes")
        if isinstance(attributs, dict):
            span["attributes"] = {
                cle: masquer_url(valeur) if cle in ("url.full", "http.url", "url") else valeur
                for cle, valeur in attributs.items()
                if isinstance(cle, str) and _attribut_permis(cle)
            }
        return span
    except Exception:  # noqa: BLE001 -- sinon le SDK enverrait le span brut
        return {"name": FILTERED, "attributes": {}}


def reglages_sentry():
    """Options de `sentry_sdk.init`, partagées par les réglages et les tests."""
    return {
        "integrations": [
            # Pas de spans de cache (sentry-sdk 3 les active par défaut).
            DjangoIntegration(cache_spans=False),
            # sentry-sdk 3 n'active plus l'intégration des journaux d'office, et
            # sans `event_level` un `logger.error()` ne crée plus d'évènement.
            # `level=None` : pas de « Sentry Logs » (jamais envoyés en 2.x).
            LoggingIntegration(level=None, event_level=logging.ERROR,
                               breadcrumb_level=logging.INFO),
        ],
        # Défaut passé à True en 3.0 : un simple message n'emporte pas de pile.
        "attach_stacktrace": False,
        # Ni PII, ni cookies, ni corps, ni variables locales : `DONNEES_COLLECTEES`.
        "data_collection": DONNEES_COLLECTEES,
        "max_request_body_size": "never",
        "before_send": avant_envoi,
        "before_send_span": avant_span,
    }

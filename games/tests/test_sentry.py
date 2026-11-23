"""Ce qui part vers Sentry (`config/sentry_filtres.py`, sentry-sdk 3).

Les tests unitaires éprouvent les filtres sur des données fabriquées ;
`SondeSentryTests` passe par un vrai client sentry-sdk, avec les réglages
mêmes de la production, et lit les enveloppes qui seraient parties.
"""

import json
import logging
import warnings

import sentry_sdk
from django.test import SimpleTestCase
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from config.sentry_filtres import avant_envoi, avant_span, reglages_sentry
from config.sentry_scrub import FILTERED

SECRETS = ("hunter2", "abc123", "k3y", "Bearer xyz", "81.2.3.4", "sessionid=")


def contient(donnees, *secrets):
    texte = json.dumps(donnees, ensure_ascii=False, default=str)
    return [s for s in secrets if s in texte]


class ReglagesTests(SimpleTestCase):
    def test_init_sans_avertissement_et_sans_collecte_de_plus(self):
        with warnings.catch_warnings(record=True) as avertissements:
            warnings.simplefilter("always")
            client = sentry_sdk.Client(dsn=None, default_integrations=False, **reglages_sentry())
        self.assertEqual([str(a.message) for a in avertissements], [])
        regles = client.options["data_collection"]
        self.assertIs(regles["user_info"], False)
        self.assertEqual(regles["cookies"], {"mode": "off"})
        self.assertEqual(regles["http_bodies"], [])
        self.assertIs(regles["stack_frame_variables"], False)
        self.assertIs(regles["database_query_data"], False)
        self.assertEqual(regles["mcp"], {"inputs": False, "outputs": False})
        self.assertIs(client.options["attach_stacktrace"], False)

    def test_integrations(self):
        django, journaux = reglages_sentry()["integrations"]
        self.assertIsInstance(django, DjangoIntegration)
        self.assertIs(django.cache_spans, False)
        self.assertIsInstance(journaux, LoggingIntegration)
        self.assertIsNone(journaux._logs_handler)  # pas de « Sentry Logs »
        self.assertEqual(journaux._event_handler.level, logging.ERROR)


class AvantEnvoiTests(SimpleTestCase):
    def test_jeton_et_mot_de_passe_masques(self):
        sortant = avant_envoi({
            "request": {"method": "POST", "url": "https://h/partie/?token=abc123",
                        "data": {"password": "hunter2"},
                        "headers": {"Authorization": "Bearer xyz", "User-Agent": "Firefox",
                                    "Cookie": "sessionid=1"}},
            "extra": {"token": "abc123", "n": 1},
            "user": {"id": 7, "ip_address": "81.2.3.4"},
            "exception": {"values": [{"type": "ValueError", "stacktrace": {"frames": [
                {"function": "f", "vars": {"password": "hunter2", "api_key": "k3y", "i": 2}}]}}]},
        }, {})
        self.assertEqual(contient(sortant, *SECRETS), [])
        self.assertEqual(sortant["request"], {"method": "POST", "url": "https://h/partie/",
                                              "headers": {"User-Agent": "Firefox"}})
        self.assertEqual(sortant["user"], {"id": "7"})
        self.assertEqual(sortant["extra"]["n"], 1)
        self.assertEqual(sortant["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["i"], 2)


class AvantSpanTests(SimpleTestCase):
    def test_jeton_masque_dans_le_nom_et_les_attributs(self):
        sortant = avant_span({"name": "GET /partie/?token=abc123", "attributes": {
            "url.full": "https://h/partie/?token=abc123", "url.query": "token=abc123",
            "http.request.header.authorization": ["Bearer xyz"],
            "http.request.header.user-agent": ["Firefox"],
            "db.query.text": "SELECT 1 -- password=hunter2", "client.address": "81.2.3.4",
            "sentry.op": "http.server"}}, {})
        self.assertEqual(contient(sortant, *SECRETS), [])
        self.assertEqual(sortant["name"], "GET /partie/?token=" + FILTERED)
        self.assertEqual(sortant["attributes"]["url.full"], "https://h/partie/")
        self.assertEqual(sortant["attributes"]["http.request.header.user-agent"], ["Firefox"])
        self.assertEqual(sortant["attributes"]["sentry.op"], "http.server")

    def test_un_span_illisible_part_vide_plutot_que_brut(self):
        class Piege(dict):
            def items(self):
                raise RuntimeError("boom")

        self.assertEqual(avant_span({"name": "x", "attributes": Piege(password="hunter2")}, {}),
                         {"name": FILTERED, "attributes": {}})


class TransportCapturant(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envois = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.envois.append(item.payload.json)
            elif item.type == "span":
                self.envois.extend(dict(s, type="span") for s in item.payload.json["items"])


class SondeSentryTests(SimpleTestCase):
    def setUp(self):
        self.transport = TransportCapturant()
        with warnings.catch_warnings(record=True) as avertissements:
            warnings.simplefilter("always")
            sentry_sdk.init(dsn="https://cle@sentry.invalid/1", transport=self.transport,
                            default_integrations=False, traces_sample_rate=1.0,
                            **reglages_sentry())
        self.assertEqual([str(a.message) for a in avertissements
                          if issubclass(a.category, DeprecationWarning)], [])

    def tearDown(self):
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)

    def test_logger_error_cree_un_evenement(self):
        logging.getLogger("games.sonde").error("Sonde %s", "valeur")
        sentry_sdk.flush()
        evenements = [e for e in self.transport.envois if e.get("type", "event") == "event"]
        self.assertEqual(len(evenements), 1)
        self.assertEqual(evenements[0]["logentry"]["message"], "Sonde %s")

    def test_variables_locales_non_envoyees(self):
        # Construit à l'exécution : le contexte source (code) ne doit pas le citer.
        password = "".join(["mot-de-", "passe-", "sonde"])
        try:
            raise ValueError("boom")
        except ValueError:
            sentry_sdk.capture_exception()
        sentry_sdk.flush()
        self.assertEqual(len(self.transport.envois), 1)
        self.assertEqual(contient(self.transport.envois, password), [])
        for exception in self.transport.envois[0]["exception"]["values"]:
            for cadre in exception["stacktrace"]["frames"]:
                self.assertNotIn("vars", cadre)

    def test_un_span_envoye_est_masque(self):
        with sentry_sdk.start_span(name="GET /partie/?token=abc123",
                                   attributes={"password": "hunter2", "url.query": "token=abc123"}):
            pass
        sentry_sdk.flush()
        spans = [e for e in self.transport.envois if e.get("type") == "span"]
        self.assertTrue(spans)
        self.assertEqual(contient(spans, *SECRETS), [])

import json
import os
import shutil
import unittest
from datetime import timedelta
from unittest import mock

import chess
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from games.joueur import CLE_SESSION
from games.models import Partie
from games.moteur import MoteurIndisponible, meilleur_coup
from games.retention import purger_parties


def coup_fixe(*ucis):
    """Un faux moteur qui joue, dans l'ordre, le premier coup légal de la liste."""
    def jouer(board, niveau):
        for uci in ucis:
            coup = chess.Move.from_uci(uci)
            if coup in board.legal_moves:
                return coup
        return next(iter(board.legal_moves))
    return jouer


class JoueurMixin:
    def nouvelle_partie(self, couleur="w", niveau=3):
        with mock.patch("games.views.meilleur_coup", side_effect=coup_fixe("e7e5", "e2e4")):
            reponse = self.client.post(reverse("nouvelle_partie"), {"couleur": couleur, "niveau": niveau})
        self.assertEqual(reponse.status_code, 302)
        return Partie.objects.latest("creee_le")

    def jouer(self, partie, de, vers, moteur=("e7e5",)):
        with mock.patch("games.views.meilleur_coup", side_effect=coup_fixe(*moteur)):
            return self.client.post(
                reverse("jouer", args=[partie.pk]),
                data=json.dumps({"de": de, "vers": vers}),
                content_type="application/json",
            )


class CreationTests(JoueurMixin, TestCase):
    def test_accueil(self):
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)

    def test_bouton_level_et_tableau_des_niveaux(self):
        reponse = self.client.get(reverse("accueil"))
        self.assertContains(reponse, 'data-bs-target="#niveaux"')
        self.assertContains(reponse, "Lichess Stockfish Level to Elo Breakdown")
        self.assertContains(reponse, "Full strength, single pv, depth 22")

    def test_le_formulaire_affiche_se_soumet_tel_quel(self):
        """Ce que la page rend (choix cochés par défaut) suffit à créer une partie."""
        import re
        page = self.client.get(reverse("accueil")).content.decode()
        couleur = re.search(r'name="couleur" value="(\w+)"[^>]*checked', page).group(1)
        niveau = re.search(r'<option value="(\d+)" selected>', page).group(1)
        reponse = self.client.post(reverse("nouvelle_partie"), {"couleur": couleur, "niveau": niveau})
        self.assertEqual(reponse.status_code, 302)

    def test_partie_avec_les_blancs(self):
        partie = self.nouvelle_partie("w")
        self.assertEqual(partie.couleur, "w")
        self.assertEqual(partie.coups, "")
        self.assertEqual(self.client.session[CLE_SESSION], partie.joueur)

    def test_avec_les_noirs_le_moteur_ouvre(self):
        partie = self.nouvelle_partie("b")
        self.assertEqual(partie.coups, "e2e4")

    def test_moteur_indisponible_a_l_ouverture(self):
        with mock.patch("games.views.meilleur_coup", side_effect=MoteurIndisponible):
            self.client.post(reverse("nouvelle_partie"), {"couleur": "b", "niveau": 3})
        partie = Partie.objects.get()
        self.assertEqual(partie.coups, "")
        with mock.patch("games.views.meilleur_coup", side_effect=coup_fixe("d2d4")):
            reponse = self.client.post(reverse("relancer_moteur", args=[partie.pk]))
        self.assertEqual(reponse.json()["coups"], ["d4"])

    def test_niveau_hors_bornes_refuse(self):
        reponse = self.client.post(reverse("nouvelle_partie"), {"couleur": "w", "niveau": 9})
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(Partie.objects.exists())


class CoupsTests(JoueurMixin, TestCase):
    def setUp(self):
        self.partie = self.nouvelle_partie("w")

    def test_coup_legal_puis_reponse_du_moteur(self):
        reponse = self.jouer(self.partie, "e2", "e4")
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        self.assertEqual(donnees["coups"], ["e4", "e5"])
        self.assertEqual(donnees["trait"], "w")
        self.assertIn("g1", donnees["legaux"])
        self.partie.refresh_from_db()
        self.assertEqual(self.partie.coups, "e2e4 e7e5")
        self.assertEqual(self.partie.fen, self.partie.echiquier().fen())

    def test_coup_illegal(self):
        reponse = self.jouer(self.partie, "e2", "e5")
        self.assertEqual(reponse.status_code, 400)
        self.partie.refresh_from_db()
        self.assertEqual(self.partie.coups, "")

    def test_coup_mal_forme(self):
        reponse = self.client.post(reverse("jouer", args=[self.partie.pk]), data="pas du json",
                                   content_type="application/json")
        self.assertEqual(reponse.status_code, 400)
        reponse = self.client.post(reverse("jouer", args=[self.partie.pk]),
                                   data=json.dumps({"de": "z9", "vers": "e4"}),
                                   content_type="application/json")
        self.assertEqual(reponse.status_code, 400)

    def test_coup_d_une_piece_adverse(self):
        reponse = self.jouer(self.partie, "e7", "e5")
        self.assertEqual(reponse.status_code, 400)

    def test_moteur_indisponible_garde_le_coup_du_joueur(self):
        with mock.patch("games.views.meilleur_coup", side_effect=MoteurIndisponible):
            reponse = self.client.post(reverse("jouer", args=[self.partie.pk]),
                                       data=json.dumps({"de": "e2", "vers": "e4"}),
                                       content_type="application/json")
        self.assertEqual(reponse.status_code, 503)
        self.assertTrue(reponse.json()["moteur_indisponible"])
        self.partie.refresh_from_db()
        self.assertEqual(self.partie.coups, "e2e4")
        # Pas au joueur : un second coup est refusé tant que le moteur n'a pas joué.
        self.assertEqual(self.jouer(self.partie, "d2", "d4").status_code, 409)

    def test_mat_du_berger(self):
        self.jouer(self.partie, "e2", "e4", moteur=("e7e5",))
        self.jouer(self.partie, "f1", "c4", moteur=("b8c6",))
        self.jouer(self.partie, "d1", "h5", moteur=("g8f6",))
        reponse = self.jouer(self.partie, "h5", "f7")
        donnees = reponse.json()
        self.assertEqual(donnees["statut"], "terminee")
        self.assertEqual(donnees["resultat"], "1-0")
        self.assertEqual(donnees["fin"], "Échec et mat")
        self.assertEqual(donnees["legaux"], {})
        self.assertEqual(self.jouer(self.partie, "a2", "a3").status_code, 409)

    def test_promotion_en_dame(self):
        # Position préparée : un pion blanc en a7, rois loin.
        self.partie.coups = ""
        self.partie.save()
        board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        with mock.patch.object(Partie, "echiquier", return_value=board):
            reponse = self.jouer(self.partie, "a7", "a8", moteur=("e8d7",))
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.json()["coups"][0].startswith("a8=Q"))

    def test_abandon(self):
        reponse = self.client.post(reverse("abandonner", args=[self.partie.pk]))
        self.assertRedirects(reponse, reverse("partie", args=[self.partie.pk]))
        self.partie.refresh_from_db()
        self.assertEqual((self.partie.statut, self.partie.resultat, self.partie.fin),
                         ("terminee", "0-1", "abandon"))

    def test_get_refuse_sur_jouer(self):
        self.assertEqual(self.client.get(reverse("jouer", args=[self.partie.pk])).status_code, 405)


class CloisonnementTests(JoueurMixin, TestCase):
    """La partie d'un autre joueur est invisible : 404, jamais 403."""

    def setUp(self):
        self.partie = self.nouvelle_partie("w")
        self.client.logout()
        self.client.cookies.clear()

    def test_page_d_une_autre_session(self):
        self.assertEqual(self.client.get(reverse("partie", args=[self.partie.pk])).status_code, 404)

    def test_coup_dans_la_partie_d_un_autre(self):
        self.client.post(reverse("nouvelle_partie"), {"couleur": "w", "niveau": 1})  # pose un jeton
        self.assertEqual(self.jouer(self.partie, "e2", "e4").status_code, 404)
        self.assertEqual(self.client.post(reverse("abandonner", args=[self.partie.pk])).status_code, 404)
        self.partie.refresh_from_db()
        self.assertEqual(self.partie.coups, "")

    def test_partie_inconnue(self):
        url = reverse("partie", args=["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_accueil_ne_liste_que_ses_parties(self):
        reponse = self.client.get(reverse("accueil"))
        self.assertNotContains(reponse, str(self.partie.pk))


class RetentionTests(JoueurMixin, TestCase):
    def test_purge_des_parties_inactives(self):
        ancienne = self.nouvelle_partie()
        recente = self.nouvelle_partie()
        Partie.objects.filter(pk=ancienne.pk).update(
            modifiee_le=timezone.now() - timedelta(days=settings.RETENTION_PARTIES_JOURS + 1))
        self.assertEqual(purger_parties(), 1)
        self.assertEqual(list(Partie.objects.values_list("pk", flat=True)), [recente.pk])


class SanteTests(TestCase):
    def test_sante_sans_stockfish(self):
        with override_settings(STOCKFISH_PATH="/nulle/part/stockfish"):
            reponse = self.client.get("/health/")
        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse.json()["checks"], {"db": {"ok": True}, "stockfish": {"ok": False}})

    def test_sante_avec_stockfish(self):
        with mock.patch("config.sante.os.path.isfile", return_value=True), \
                mock.patch("config.sante.os.access", return_value=True):
            reponse = self.client.get("/health/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["status"], "ok")


def _stockfish_present():
    chemin = settings.STOCKFISH_PATH
    return os.path.isfile(chemin) or shutil.which(chemin) is not None


@unittest.skipUnless(_stockfish_present(), "Stockfish absent (STOCKFISH_PATH) — lancé en CI")
class MoteurReelTests(TestCase):
    """Le vrai Stockfish : installé en CI (`apt install stockfish`)."""

    def test_chaque_niveau_joue_un_coup_legal(self):
        board = chess.Board()
        for niveau in range(1, 9):
            self.assertIn(meilleur_coup(board, niveau), board.legal_moves)

    def test_trouve_le_mat_en_un(self):
        board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
        self.assertEqual(meilleur_coup(board, 8), chess.Move.from_uci("a1a8"))

    @override_settings(STOCKFISH_PATH="/nulle/part/stockfish")
    def test_binaire_absent(self):
        with self.assertRaises(MoteurIndisponible):
            meilleur_coup(chess.Board(), 1)

"""La 2FA de l'admin (admin_2fa/) ne change rien au site public, même pour un admin."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from games.tests.test_parties import JoueurMixin


class SitePublicInchangeTests(JoueurMixin, TestCase):
    def _admin(self, enrole):
        admin = get_user_model().objects.create_user(email="ops@example.com", password="sup3rSecret!")
        admin.is_staff = True
        admin.save()
        if enrole:
            TOTPDevice.objects.create(user=admin, name="admin-2fa", confirmed=True)
        return admin

    def test_un_admin_sans_second_facteur_joue_normalement(self):
        for enrole in (False, True):
            with self.subTest(enrole=enrole):
                get_user_model().objects.all().delete()
                self.client.force_login(self._admin(enrole))  # mot de passe seul, pas de 2FA
                self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)
                partie = self.nouvelle_partie("w")
                self.assertEqual(self.client.get(reverse("partie", args=[partie.pk])).status_code, 200)
                self.assertEqual(self.jouer(partie, "e2", "e4").status_code, 200)
                # …mais l'admin lui reste fermé.
                self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_health_reste_public(self):
        with mock.patch("config.sante.os.path.isfile", return_value=True), \
                mock.patch("config.sante.os.access", return_value=True):
            self.assertEqual(self.client.get("/health/").status_code, 200)

"""Purge RGPD (OPERATIONS.md §3.25) : les parties sans activité depuis
`RETENTION_PARTIES_JOURS` jours sont effacées. Les sessions expirées, elles,
sont effacées par `clearsessions` (même minuterie)."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from games.models import Partie


def purger_parties(maintenant=None):
    """Efface les parties inactives ; renvoie le nombre de parties effacées."""
    limite = (maintenant or timezone.now()) - timedelta(days=settings.RETENTION_PARTIES_JOURS)
    nombre, _ = Partie.objects.filter(modifiee_le__lt=limite).delete()
    return nombre

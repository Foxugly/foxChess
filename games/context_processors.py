import os

from django.conf import settings
from django.utils import timezone


def application(request):
    """Version et année du footer (standard de la flotte)."""
    return {
        "application": {
            "version": os.environ.get("SENTRY_RELEASE", "")[:7] or settings.VERSION,
            "annee": timezone.now().year,
        }
    }

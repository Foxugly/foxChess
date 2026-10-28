"""`/health/` : ce que surveille UptimeRobot (OPERATIONS.md §3.9).

Contrôle réel de ses dépendances (§3.19, « a health check that does not
exercise its dependency is worthless ») : la base (`SELECT 1`) et le binaire
Stockfish (présent et exécutable — le lancer toutes les cinq minutes coûterait
pour rien). 503 si l'une manque. Public, sans rien de confidentiel.
"""

import os

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def sante(request):
    try:
        with connection.cursor() as curseur:
            curseur.execute("SELECT 1")
            curseur.fetchone()
        base_ok = True
    except DatabaseError:
        base_ok = False
    chemin = settings.STOCKFISH_PATH
    moteur_ok = os.path.isfile(chemin) and os.access(chemin, os.X_OK)
    tout_ok = base_ok and moteur_ok
    return JsonResponse(
        {
            "status": "ok" if tout_ok else "degraded",
            "version": os.environ.get("SENTRY_RELEASE") or settings.VERSION,
            "checks": {"db": {"ok": base_ok}, "stockfish": {"ok": moteur_ok}},
        },
        status=200 if tout_ok else 503,
    )

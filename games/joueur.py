"""Le joueur anonyme : un jeton aléatoire gardé dans la session.

Pas la clé de session elle-même : Django la renouvelle (connexion d'un
administrateur, `cycle_key`), et le joueur perdrait ses parties. Le jeton,
lui, reste tant que la session vit.
"""

import secrets

CLE_SESSION = "foxchess_joueur"


def jeton_du_joueur(request, creer=False):
    """Le jeton de la session ; `None` s'il n'y en a pas et que `creer` est faux."""
    jeton = request.session.get(CLE_SESSION)
    if jeton is None and creer:
        jeton = secrets.token_hex(16)
        request.session[CLE_SESSION] = jeton
    return jeton

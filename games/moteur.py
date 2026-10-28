"""Stockfish, par python-chess (protocole UCI).

Un processus par coup, arrêté aussitôt : rien ne reste en mémoire entre deux
requêtes, et un moteur planté ne survit pas à la requête qui l'a lancé. Le
démarrage coûte quelques dizaines de millisecondes, négligeables à côté du
temps de réflexion.

Les niveaux 1 à 8 combinent l'option `Skill Level` (0–20) de Stockfish, une
profondeur maximale et un temps de réflexion. Les bas niveaux sont surtout
bridés par la profondeur : `Skill Level` seul joue encore trop bien.
"""

from dataclasses import dataclass

import chess
import chess.engine
from django.conf import settings


@dataclass(frozen=True)
class Niveau:
    skill: int
    profondeur: int | None
    temps: float


NIVEAUX = {
    1: Niveau(skill=0, profondeur=1, temps=0.05),
    2: Niveau(skill=3, profondeur=2, temps=0.05),
    3: Niveau(skill=6, profondeur=4, temps=0.1),
    4: Niveau(skill=9, profondeur=6, temps=0.15),
    5: Niveau(skill=12, profondeur=8, temps=0.2),
    6: Niveau(skill=15, profondeur=12, temps=0.4),
    7: Niveau(skill=18, profondeur=16, temps=0.7),
    8: Niveau(skill=20, profondeur=None, temps=1.0),
}

#: Au-delà, le moteur est considéré comme bloqué (démarrage + réflexion).
DELAI_MAX = 10.0


class MoteurIndisponible(Exception):
    """Stockfish absent, planté ou trop lent : la requête répond 503."""


def meilleur_coup(board, niveau):
    """Le coup de Stockfish dans la position `board` au niveau `niveau` (1–8)."""
    reglage = NIVEAUX[niveau]
    try:
        moteur = chess.engine.SimpleEngine.popen_uci(settings.STOCKFISH_PATH, timeout=DELAI_MAX)
    except (OSError, chess.engine.EngineError, TimeoutError) as erreur:
        raise MoteurIndisponible("Stockfish ne démarre pas") from erreur
    try:
        moteur.configure({
            "Threads": settings.STOCKFISH_THREADS,
            "Hash": settings.STOCKFISH_HASH_MB,
            "Skill Level": reglage.skill,
        })
        resultat = moteur.play(
            board,
            chess.engine.Limit(time=reglage.temps, depth=reglage.profondeur),
        )
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, TimeoutError) as erreur:
        raise MoteurIndisponible("Stockfish n'a pas répondu") from erreur
    finally:
        try:
            moteur.quit()
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, TimeoutError):
            moteur.close()
    if resultat.move is None or resultat.move not in board.legal_moves:
        raise MoteurIndisponible("Stockfish n'a pas proposé de coup légal")
    return resultat.move

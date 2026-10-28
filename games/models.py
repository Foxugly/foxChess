"""Une partie contre Stockfish.

La partie est rejouée depuis sa liste de coups (UCI) : python-chess reconstruit
l'échiquier, vérifie chaque coup et dit si la partie est finie. La position
FEN stockée n'est qu'un cache pour l'affichage et l'administration ; la
vérité, c'est `coups`.

Pas de compte : une partie appartient au jeton `joueur` posé dans la session
(games/joueur.py). Toute partie d'un autre jeton répond 404.
"""

import uuid

import chess
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

NIVEAU_MIN = 1
NIVEAU_MAX = 8


class Partie(models.Model):
    class Couleur(models.TextChoices):
        BLANCS = "w", "Blancs"
        NOIRS = "b", "Noirs"

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        TERMINEE = "terminee", "Terminée"

    class Fin(models.TextChoices):
        MAT = "mat", "Échec et mat"
        PAT = "pat", "Pat"
        MATERIEL = "materiel", "Matériel insuffisant"
        CINQUANTE_COUPS = "cinquante_coups", "Règle des 50 coups"
        REPETITION = "repetition", "Triple répétition"
        ABANDON = "abandon", "Abandon"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    joueur = models.CharField(max_length=64, db_index=True)
    couleur = models.CharField(max_length=1, choices=Couleur.choices, default=Couleur.BLANCS)
    niveau = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(NIVEAU_MIN), MaxValueValidator(NIVEAU_MAX)])
    coups = models.TextField(blank=True, default="")
    fen = models.CharField(max_length=100, default=chess.STARTING_FEN)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_COURS)
    resultat = models.CharField(max_length=7, default="*")
    fin = models.CharField(max_length=20, choices=Fin.choices, blank=True, default="")
    creee_le = models.DateTimeField(auto_now_add=True)
    modifiee_le = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-modifiee_le"]
        verbose_name = "partie"
        verbose_name_plural = "parties"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(niveau__gte=NIVEAU_MIN, niveau__lte=NIVEAU_MAX),
                name="partie_niveau_borne",
            ),
        ]

    def __str__(self):
        return f"Partie {self.id} ({self.get_couleur_display()}, niveau {self.niveau})"

    # --- Échiquier ----------------------------------------------------------

    def liste_coups(self):
        return self.coups.split()

    def echiquier(self):
        """L'échiquier rejoué depuis le début ; lève ValueError si un coup stocké est faux."""
        board = chess.Board()
        for uci in self.liste_coups():
            coup = chess.Move.from_uci(uci)
            if coup not in board.legal_moves:
                raise ValueError(f"Coup stocké illégal : {uci}")
            board.push(coup)
        return board

    @property
    def couleur_joueur(self):
        return chess.WHITE if self.couleur == self.Couleur.BLANCS else chess.BLACK

    @property
    def en_cours(self):
        return self.statut == self.Statut.EN_COURS

    def jouer(self, board, coup):
        """Ajoute `coup` (déjà vérifié légal sur `board`) et met fin à la partie s'il le faut."""
        board.push(coup)
        self.coups = " ".join([*self.liste_coups(), coup.uci()])
        self.fen = board.fen()
        self._constater_fin(board)

    def abandonner(self):
        self.statut = self.Statut.TERMINEE
        self.fin = self.Fin.ABANDON
        self.resultat = "0-1" if self.couleur_joueur == chess.WHITE else "1-0"

    def _constater_fin(self, board):
        # `claim_draw=True` : la triple répétition et les 50 coups mettent fin à
        # la partie sans que personne ait à la réclamer — un moteur la
        # réclamerait de toute façon, et le joueur n'a pas de bouton pour ça.
        issue = board.outcome(claim_draw=True)
        if issue is None:
            return
        self.statut = self.Statut.TERMINEE
        self.resultat = issue.result()
        self.fin = {
            chess.Termination.CHECKMATE: self.Fin.MAT,
            chess.Termination.STALEMATE: self.Fin.PAT,
            chess.Termination.INSUFFICIENT_MATERIAL: self.Fin.MATERIEL,
            chess.Termination.FIFTY_MOVES: self.Fin.CINQUANTE_COUPS,
            chess.Termination.SEVENTYFIVE_MOVES: self.Fin.CINQUANTE_COUPS,
            chess.Termination.THREEFOLD_REPETITION: self.Fin.REPETITION,
            chess.Termination.FIVEFOLD_REPETITION: self.Fin.REPETITION,
        }.get(issue.termination, "")

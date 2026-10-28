"""Pages et échanges JSON d'une partie.

Règles :
- une partie d'un autre joueur, ou inconnue, répond **404** (jamais 403 : ne
  pas confirmer qu'elle existe) ;
- le serveur est seul juge de la légalité d'un coup (python-chess) ; le
  navigateur ne reçoit que la liste des coups légaux, pour l'ergonomie ;
- chaque coup est joué sous verrou de ligne (`select_for_update`) : deux
  requêtes simultanées sur la même partie ne peuvent pas jouer deux coups
  depuis la même position.
"""

import json
import random

import chess
from django import forms
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from games.joueur import jeton_du_joueur
from games.models import NIVEAU_MAX, NIVEAU_MIN, Partie
from games.moteur import MoteurIndisponible, meilleur_coup

PARTIES_LISTEES = 10


class NouvellePartieForm(forms.Form):
    couleur = forms.ChoiceField(
        choices=[("w", "Blancs"), ("b", "Noirs"), ("hasard", "Au hasard")], initial="w",
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}))
    niveau = forms.TypedChoiceField(
        coerce=int, initial=3,
        choices=[(n, str(n)) for n in range(NIVEAU_MIN, NIVEAU_MAX + 1)])


def _partie_du_joueur(request, pk, verrou=False):
    jeton = jeton_du_joueur(request)
    if jeton is None:
        raise Http404
    parties = Partie.objects.filter(joueur=jeton)
    if verrou:
        parties = parties.select_for_update()
    try:
        return parties.get(pk=pk)
    except Partie.DoesNotExist:
        raise Http404 from None


def etat(partie, board=None):
    """Ce que le navigateur sait d'une partie : position, coups, coups légaux."""
    board = board or partie.echiquier()
    a_lui = partie.en_cours and board.turn == partie.couleur_joueur
    legaux = {}
    if a_lui:
        for coup in board.legal_moves:
            legaux.setdefault(chess.square_name(coup.from_square), []).append(
                chess.square_name(coup.to_square))
    # Les coups en notation algébrique, rejoués depuis le début.
    rejeu = board.root()
    san = []
    for coup in board.move_stack:
        san.append(rejeu.san(coup))
        rejeu.push(coup)
    dernier = board.move_stack[-1] if board.move_stack else None
    return {
        "fen": board.fen(),
        "coups": san,
        "trait": "w" if board.turn == chess.WHITE else "b",
        "echec": board.is_check(),
        "legaux": dict(sorted((k, sorted(v)) for k, v in legaux.items())),
        "dernier": {"de": chess.square_name(dernier.from_square),
                    "vers": chess.square_name(dernier.to_square)} if dernier else None,
        "statut": partie.statut,
        "resultat": partie.resultat,
        "fin": partie.get_fin_display() if partie.fin else "",
    }


@require_GET
def accueil(request):
    jeton = jeton_du_joueur(request)
    parties = Partie.objects.filter(joueur=jeton)[:PARTIES_LISTEES] if jeton else []
    return render(request, "games/accueil.html", {
        "form": NouvellePartieForm(),
        "parties": parties,
    })


@require_POST
def nouvelle_partie(request):
    form = NouvellePartieForm(request.POST)
    if not form.is_valid():
        jeton = jeton_du_joueur(request)
        parties = Partie.objects.filter(joueur=jeton)[:PARTIES_LISTEES] if jeton else []
        return render(request, "games/accueil.html", {"form": form, "parties": parties}, status=400)
    couleur = form.cleaned_data["couleur"]
    if couleur == "hasard":
        couleur = random.choice(["w", "b"])
    partie = Partie(
        joueur=jeton_du_joueur(request, creer=True),
        couleur=couleur,
        niveau=form.cleaned_data["niveau"],
    )
    partie.save()
    # Avec les noirs, le moteur ouvre. S'il est indisponible, la partie
    # existe quand même : la page le dira et proposera de réessayer.
    if partie.couleur == Partie.Couleur.NOIRS:
        try:
            _coup_du_moteur(partie, partie.echiquier())
            partie.save()
        except MoteurIndisponible:
            pass
    return redirect("partie", pk=partie.pk)


@require_GET
def partie(request, pk):
    partie = _partie_du_joueur(request, pk)
    return render(request, "games/partie.html", {"partie": partie, "etat": etat(partie)})


def _coup_du_moteur(partie, board):
    coup = meilleur_coup(board, partie.niveau)
    partie.jouer(board, coup)


def _erreur(message, status):
    return JsonResponse({"erreur": message}, status=status)


@require_POST
def jouer(request, pk):
    try:
        donnees = json.loads(request.body or b"{}")
        de = chess.parse_square(donnees["de"])
        vers = chess.parse_square(donnees["vers"])
    except (ValueError, KeyError, TypeError):
        return _erreur("Coup mal formé.", 400)
    with transaction.atomic():
        partie = _partie_du_joueur(request, pk, verrou=True)
        if not partie.en_cours:
            return _erreur("La partie est terminée.", 409)
        board = partie.echiquier()
        if board.turn != partie.couleur_joueur:
            return _erreur("Ce n'est pas à vous de jouer.", 409)
        # Promotion : en dame, toujours (l'interface ne propose pas le choix).
        coup = chess.Move(de, vers)
        if coup not in board.legal_moves:
            coup = chess.Move(de, vers, promotion=chess.QUEEN)
        if coup not in board.legal_moves:
            return _erreur("Coup illégal.", 400)
        partie.jouer(board, coup)
        if partie.en_cours:
            try:
                _coup_du_moteur(partie, board)
            except MoteurIndisponible:
                # Le coup du joueur est gardé ; le moteur jouera à la requête suivante.
                partie.save()
                return JsonResponse({**etat(partie, board), "moteur_indisponible": True}, status=503)
        partie.save()
        return JsonResponse(etat(partie, board))


@require_POST
def relancer_moteur(request, pk):
    """Le moteur joue s'il doit jouer — après une indisponibilité."""
    with transaction.atomic():
        partie = _partie_du_joueur(request, pk, verrou=True)
        board = partie.echiquier()
        if partie.en_cours and board.turn != partie.couleur_joueur:
            try:
                _coup_du_moteur(partie, board)
            except MoteurIndisponible:
                return JsonResponse({**etat(partie, board), "moteur_indisponible": True}, status=503)
            partie.save()
        return JsonResponse(etat(partie, board))


@require_POST
def abandonner(request, pk):
    with transaction.atomic():
        partie = _partie_du_joueur(request, pk, verrou=True)
        if partie.en_cours:
            partie.abandonner()
            partie.save()
    return redirect("partie", pk=partie.pk)

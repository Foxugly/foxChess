/*
 * foxChess — l'échiquier d'une partie (chessboard.js).
 *
 * Le serveur est seul juge : il envoie la position, les coups joués et, quand
 * c'est au joueur, la liste des coups légaux (case de départ → cases
 * d'arrivée). Le navigateur ne fait que refuser d'avance un coup absent de
 * cette liste, envoyer le coup, puis afficher la réponse — coup du moteur
 * compris. Aucune règle des échecs n'est recodée ici.
 */
"use strict";
(function () {
    const conteneur = document.getElementById("echiquier");
    if (!conteneur) { return; }
    const statut = document.getElementById("statut");
    const listeCoups = document.getElementById("coups");
    const relancer = document.getElementById("relancer");
    const couleur = conteneur.dataset.couleur;
    let etat = JSON.parse(document.getElementById("etat-initial").textContent);
    let enAttente = false;

    function afficherStatut() {
        if (etat.statut === "terminee") {
            statut.textContent = "Partie terminée : " + etat.resultat + (etat.fin ? " (" + etat.fin + ")" : "");
        } else if (enAttente) {
            statut.textContent = "Stockfish réfléchit…";
        } else if (etat.trait === couleur) {
            statut.textContent = etat.echec ? "Échec ! À vous de jouer." : "À vous de jouer.";
        } else {
            statut.textContent = "Au tour de Stockfish.";
        }
    }

    function afficherCoups() {
        listeCoups.replaceChildren();
        for (let i = 0; i < etat.coups.length; i += 2) {
            const li = document.createElement("li");
            li.className = "list-group-item py-1";
            li.textContent = etat.coups[i] + (etat.coups[i + 1] ? "  " + etat.coups[i + 1] : "");
            listeCoups.appendChild(li);
        }
        listeCoups.scrollTop = listeCoups.scrollHeight;
    }

    function surlignerDernier() {
        conteneur.querySelectorAll(".case-dernier").forEach(function (c) { c.classList.remove("case-dernier"); });
        if (!etat.dernier) { return; }
        [etat.dernier.de, etat.dernier.vers].forEach(function (nom) {
            const c = conteneur.querySelector(".square-" + nom);
            if (c) { c.classList.add("case-dernier"); }
        });
    }

    function appliquer(nouvelEtat) {
        etat = nouvelEtat;
        board.position(etat.fen, false);
        afficherCoups();
        afficherStatut();
        surlignerDernier();
        relancer.classList.toggle("d-none", !etat.moteur_indisponible);
    }

    function envoyer(url, corps) {
        enAttente = true;
        afficherStatut();
        return fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": conteneur.dataset.csrf},
            credentials: "same-origin",
            body: JSON.stringify(corps || {}),
        }).then(function (reponse) {
            return reponse.json().catch(function () { return {}; }).then(function (donnees) {
                enAttente = false;
                if (donnees.fen) {
                    appliquer(donnees);
                    if (donnees.moteur_indisponible) {
                        statut.textContent = "Stockfish est indisponible pour le moment.";
                    }
                } else {
                    board.position(etat.fen, false);
                    afficherStatut();
                    statut.textContent = donnees.erreur || "Erreur du serveur (" + reponse.status + ").";
                }
            });
        }).catch(function () {
            enAttente = false;
            board.position(etat.fen, false);
            statut.textContent = "Connexion perdue : réessayez.";
        });
    }

    function peutJouer(piece) {
        return !enAttente && etat.statut === "en_cours" && etat.trait === couleur
            && piece.charAt(0) === couleur;
    }

    const board = Chessboard("echiquier", {
        position: etat.fen,
        orientation: couleur === "b" ? "black" : "white",
        draggable: true,
        pieceTheme: conteneur.dataset.pieces + "{piece}.png",
        onDragStart: function (source, piece) {
            return peutJouer(piece) && Object.prototype.hasOwnProperty.call(etat.legaux, source);
        },
        onDrop: function (source, cible) {
            const cibles = etat.legaux[source] || [];
            if (cibles.indexOf(cible) === -1) { return "snapback"; }
            envoyer(conteneur.dataset.urlJouer, {de: source, vers: cible});
        },
        // Roque, prise en passant, promotion : la position du serveur fait foi.
        onSnapEnd: function () { board.position(etat.fen, false); },
    });

    relancer.addEventListener("click", function () { envoyer(conteneur.dataset.urlMoteur); });
    window.addEventListener("resize", function () { board.resize(); surlignerDernier(); });

    afficherCoups();
    afficherStatut();
    surlignerDernier();
    // La partie a été créée avec les noirs mais le moteur n'a pas pu ouvrir.
    if (etat.statut === "en_cours" && etat.trait !== couleur) {
        relancer.classList.remove("d-none");
    }
})();

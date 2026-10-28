/*
 * foxChess — l'échiquier d'une partie (chessboard.js).
 *
 * Le serveur est seul juge : il envoie la position, les coups joués et, quand
 * c'est au joueur, la liste des coups légaux (case de départ → cases
 * d'arrivée). Le navigateur ne fait que refuser d'avance un coup absent de
 * cette liste, envoyer le coup, puis afficher la réponse — coup du moteur
 * compris. Aucune règle des échecs n'est recodée ici.
 *
 * Sur téléphone, le doigt cache la pièce qu'il glisse : on peut aussi toucher
 * la pièce (ses cases d'arrivée s'affichent) puis toucher sa case d'arrivée.
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
    let choisie = null;
    let glisse = false;

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

    function cibles(source) {
        return etat.legaux[source] || [];
    }

    function marquerChoix() {
        conteneur.querySelectorAll(".case-choisie, .case-cible").forEach(function (c) {
            c.classList.remove("case-choisie", "case-cible", "case-prise");
        });
        if (!choisie) { return; }
        const position = board.position();
        conteneur.querySelector(".square-" + choisie).classList.add("case-choisie");
        cibles(choisie).forEach(function (nom) {
            const c = conteneur.querySelector(".square-" + nom);
            if (c) { c.classList.add("case-cible"); c.classList.toggle("case-prise", nom in position); }
        });
    }

    function choisir(source) {
        choisie = source;
        marquerChoix();
    }

    function appliquer(nouvelEtat) {
        etat = nouvelEtat;
        choisie = null;
        board.position(etat.fen, false);
        afficherCoups();
        afficherStatut();
        surlignerDernier();
        marquerChoix();
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

    function jouer(source, cible) {
        choisir(null);
        envoyer(conteneur.dataset.urlJouer, {de: source, vers: cible});
    }

    const board = Chessboard("echiquier", {
        position: etat.fen,
        orientation: couleur === "b" ? "black" : "white",
        draggable: true,
        pieceTheme: conteneur.dataset.pieces + "{piece}.png",
        onDragStart: function (source, piece) {
            glisse = peutJouer(piece) && Object.prototype.hasOwnProperty.call(etat.legaux, source);
            return glisse;
        },
        onDrop: function (source, cible) {
            glisse = false;
            // Pièce touchée puis relâchée sur place : elle est choisie (ou plus).
            if (cible === source) {
                choisir(choisie === source ? null : source);
                return "snapback";
            }
            if (cibles(source).indexOf(cible) === -1) {
                choisir(null);
                return "snapback";
            }
            jouer(source, cible);
        },
        // Roque, prise en passant, promotion : la position du serveur fait foi.
        onSnapEnd: function () { board.position(etat.fen, false); },
    });

    // Case d'arrivée touchée (vide ou pièce adverse). Les pièces du joueur sont
    // gérées par onDrop. Au toucher, pointerup vise la case où le doigt s'est posé.
    conteneur.addEventListener("pointerup", function (e) {
        const caseTouchee = e.target.closest("[data-square]");
        // À la souris, pointerup précède la fin du glisser : onDrop s'en charge.
        if (glisse || !choisie || !caseTouchee) { return; }
        const nom = caseTouchee.getAttribute("data-square");
        const piece = board.position()[nom];
        if (piece && piece.charAt(0) === couleur) { return; }
        if (cibles(choisie).indexOf(nom) === -1 || enAttente) {
            choisir(null);
            return;
        }
        const source = choisie;
        board.move(source + "-" + nom);
        jouer(source, nom);
    });
    // Sans cela, le navigateur rejoue le toucher en clic souris : la pièce
    // serait choisie puis aussitôt relâchée.
    conteneur.addEventListener("touchend", function (e) { e.preventDefault(); }, {passive: false});

    relancer.addEventListener("click", function () { envoyer(conteneur.dataset.urlMoteur); });
    window.addEventListener("resize", function () { board.resize(); surlignerDernier(); marquerChoix(); });

    afficherCoups();
    afficherStatut();
    surlignerDernier();
    // La partie a été créée avec les noirs mais le moteur n'a pas pu ouvrir.
    if (etat.statut === "en_cours" && etat.trait !== couleur) {
        relancer.classList.remove("d-none");
    }
})();

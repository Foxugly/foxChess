# foxChess

Jouer aux échecs contre Stockfish dans le navigateur — https://foxchess.foxugly.com

- **Django 6.1** (rendu côté serveur), **python-chess** pour les règles, **Stockfish** par UCI,
  **chessboard.js** pour l'échiquier.
- Sans compte : les parties sont liées au navigateur et effacées après 30 jours sans activité.
- Huit niveaux, des blancs ou des noirs, promotion automatique en dame.

Développement : voir `CLAUDE.md`. Mise en service sur la flotte Foxugly : `deploy/README.md`.

Pièces : jeu « wikipedia » de chessboard.js (Cburnett, CC BY-SA 3.0).
chessboard.js © Chris Oakman, licence MIT.

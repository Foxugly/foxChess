# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**foxChess** is a single-site Django 6.1 app, server-rendered (no Angular tier, like Chronos):
play chess against **Stockfish** in the browser. **chessboard.js** (+ jQuery) draws the board,
**python-chess** is the only judge of legality and game end, and Stockfish is driven over UCI
by python-chess. Fleet site: `foxchess.foxugly.com`, gunicorn on **127.0.0.1:8012**, SSM
prefix `/foxchess/prod`, no Redis. Onboarding steps: `deploy/README.md`.

The interface is **French only** (no i18n catalogues yet).

## Commands

Windows-first locally; always call the venv's own Python. `DJANGO_DEBUG=True` is required for
every local command (settings fail closed without it: no dev `SECRET_KEY`, no SQLite).

```powershell
$env:DJANGO_DEBUG="True"
$env:STOCKFISH_PATH="$PWD\tools\stockfish\stockfish\stockfish-windows-x86-64-universal.exe"
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe manage.py test games
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check .
```

`tools/` is git-ignored: download the official Windows build there
(`gh release download sf_19 --repo official-stockfish/Stockfish -p stockfish-windows-x86-64-universal.zip`).
Without `STOCKFISH_PATH`, the three real-engine tests (`MoteurReelTests`) are **skipped**;
CI installs Ubuntu's `stockfish` package and **fails** if they are skipped there.

## Architecture

- **`games/models.py` — `Partie`.** The truth is `coups` (space-separated UCI); `echiquier()`
  replays it through python-chess and refuses an illegal stored move. `fen` is only a cache.
  `jouer()` pushes a move and records the end (`outcome(claim_draw=True)`).
- **`games/moteur.py` — `meilleur_coup(board, niveau)`.** One Stockfish process **per move**,
  quit right after; levels 1–8 map to `Skill Level` + depth + time (`NIVEAUX`). Any failure
  raises `MoteurIndisponible` → the view answers **503** and keeps the player's move; the
  page shows « Relancer le moteur » (`relancer_moteur`).
- **`games/views.py`.** JSON move endpoint `POST /parties/<uuid>/jouer/` `{"de","vers"}`;
  promotion is always to a queen. Each move runs under `select_for_update` so two concurrent
  requests can't both move from the same position. The browser only gets the legal-move map
  (`etat()["legaux"]`) for UX — never trust it server-side.
- **No accounts for players.** A game belongs to a random token in the session
  (`games/joueur.py`, not the session key, which rotates). **Another player's game → 404,
  never 403.** Only admins have accounts: email-only `accounts.User` (OPERATIONS.md §3.16).
- **GDPR:** `manage.py purger_parties` (daily `foxchess-purge.timer`) deletes games idle for
  `RETENTION_PARTIES_JOURS` (30) and expired sessions.
- **`/health/`** checks the DB **and** that the Stockfish binary exists and is executable.
- **CSP:** scripts only from `'self'` or with the nonce. jQuery, chessboard.js and Bootstrap JS
  are vendored in `static/vendor/` with SRI hashes on the tags — if you replace a file, recompute
  the hash (`openssl dgst -sha384 -binary f | openssl base64 -A`). Inline styles stay allowed
  (chessboard.js sizes squares with `style` attributes).
- **Load bounds:** gunicorn 2 workers, unit `CPUQuota=150%`/`MemoryMax=768M`, Stockfish 1 thread
  / 16 MB hash, nginx `limit_req` 2 r/s per IP on the endpoints that start the engine.

## Deploy

Fleet model (`OPERATIONS.md §3.11`): push to `main` → CI green → `deploy.yml` (OIDC →
`foxchess-deploy` → SSM). Root installs units, the env-fetch script and the vhost **from its
own bare mirror** `/var/lib/fleet-deploy/foxChess.git` at the pushed SHA; `deploy/ssm-deploy.sh`
runs as django. sudoers, Stockfish, DB and first clone are root, out-of-band (`deploy/README.md`).

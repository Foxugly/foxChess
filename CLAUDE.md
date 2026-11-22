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
.\.venv\Scripts\python.exe manage.py test           # all apps, as CI
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check .
```

`tools/` is git-ignored: download the official Windows build there
(`gh release download sf_19 --repo official-stockfish/Stockfish -p stockfish-windows-x86-64-universal.zip`).
Without `STOCKFISH_PATH`, the three real-engine tests (`MoteurReelTests`) are **skipped**;
CI installs Ubuntu's `stockfish` package and **fails** if they are skipped there.

Dependencies: direct ones (ranges) live in **`requirements.in`**; **`requirements.txt` is a hash-pinned lock**
generated from it by uv for Linux / Python 3.14 (production, deadsnakes `/usr/bin/python3.14`) — the deploy installs exactly that
(`--require-hashes --no-deps`, then `pip check`). After editing `requirements.in`, regenerate the lock with the
command in its header (`uv pip compile requirements.in --generate-hashes --python-version 3.14
--python-platform x86_64-unknown-linux-gnu -o requirements.txt`). On Linux (CI) install in two steps —
`pip install --require-hashes -r requirements.txt` then `pip install -r requirements-dev.txt` (one hashed line
puts pip in hash-checking mode for the whole install). **On Windows the lock does not install** (no `tzdata`, a
Windows-only Django dependency): `.\.venv\Scripts\python.exe -m pip install -r requirements.in -r requirements-dev.txt`.

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
- **Static files**: `config.stockage.StatiquesHaches` (ManifestStaticFilesStorage with `patterns = ()`)
  hashes file names for cache-busting but never rewrites contents (SRI hashes stay valid). `manage.py test`
  falls back to plain `StaticFilesStorage` (no manifest without collectstatic). A `{% static %}` on a
  directory fails in prod — use `{% get_static_prefix %}` (as for the chessboard.js pieces).
- **Load bounds:** gunicorn 2 workers, unit `CPUQuota=150%`/`MemoryMax=768M`, Stockfish 1 thread
  / 16 MB hash, nginx `limit_req` 2 r/s per IP on the endpoints that start the engine.

## Admin 2FA

`/admin/` requires a TOTP second factor for **every** staff account (django-otp 1.7.5 + qrcode 8.2,
app `admin_2fa/`, ported from the fleet reference Poker_server). Players see nothing of it.

- **Wiring**: `"admin_2fa.apps.OTPAdminConfig"` *replaces* `"django.contrib.admin"` (it makes
  `admin.site` an `Admin2FASite`, whose `has_permission` also needs `user.is_verified()`); plus
  `django_otp`, `otp_totp`, `otp_static`, `admin_2fa` in INSTALLED_APPS and
  `django_otp.middleware.OTPMiddleware` right after `AuthenticationMiddleware`. `OTP_TOTP_ISSUER` is
  the label in the authenticator app. A missing piece fails `manage.py check` (`admin_2fa.E001-E004`).
  A custom `AdminSite` subclass must inherit `Admin2FASite`.
- **Flow**: password on `/admin/login/` → `/admin/2fa/setup/` (first time: QR code + key, confirm one
  code, 10 single-use backup codes shown **once**) or `/admin/2fa/verify/` (TOTP code or a backup
  code). Server-rendered templates, CSRF, `never_cache`, no inline script/style (CSP-safe).
- **Brute force**: django-otp throttles each device (1 s, 2 s, 4 s… after each wrong code) and nginx
  puts `/admin/2fa/` in the same `foxchess_admin_login` zone as the login (10 r/min per IP).
- **Lost phone / locked out** (on the box, as the app's own unit would run it):

  ```bash
  sudo systemd-run --wait --pipe --quiet --uid=django --gid=www-data \
    -p EnvironmentFile=/run/foxchess/.env -p WorkingDirectory=/var/www/django_websites/foxChess \
    /var/www/django_websites/foxChess/.venv/bin/python manage.py admin_2fa_reset <email>
  ```

  deletes the user's devices (re-enrolment at the next admin login); `--unlock` only clears the delay.
- **Tests on admin pages**: use `admin_2fa.testing.force_admin_login(client, user)`, not
  `client.force_login` (the admin would redirect to the second factor). The admin_2fa tests are
  Django `TestCase`s (the reference ones are pytest); CI runs `manage.py test` on **all** apps.
- **Secrets**: never log or send to Sentry the TOTP key, the QR code or a backup code — the views keep
  them in `Redacted` wrappers and the form field is named `token` (scrubbed by Sentry).

## Deploy

Fleet model (`OPERATIONS.md §3.11`): push to `main` → CI green → `deploy.yml` (OIDC →
`foxchess-deploy` → SSM). Root installs units, the env-fetch script and the vhost **from its
own bare mirror** `/var/lib/fleet-deploy/foxChess.git` at the pushed SHA; `deploy/ssm-deploy.sh`
runs as django. sudoers, Stockfish, DB and first clone are root, out-of-band (`deploy/README.md`).

The venv runs on **`/usr/bin/python3.14`** (deadsnakes; the system `python3` stays 3.12).
`ssm-deploy.sh` checks the venv's version before `pip install`: on a mismatch it rebuilds `.venv`
**in place** (console-script shebangs hard-code the path), keeps the old one as `.venv.prev` and
puts it back if the rebuild fails.

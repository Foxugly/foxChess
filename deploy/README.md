# Mise en service de foxChess sur la flotte (foxchess.foxugly.com)

Référence : `OPERATIONS.md` (dépôt `Foxugly/foxugly-ops`), §3.12 « nouveau site », et
QuizOnline, l'implémentation de référence ; repris de Chronos pour la forme (Django rendu
côté serveur). Port **8012**, gunicorn (WSGI : pas de WebSocket), base PostgreSQL 16 locale,
application dans `/var/www/django_websites/foxChess` (la racine du dépôt est la racine Django).
**Pas de Redis.**

Ce qui est versionné ici et installé **par le déploiement**, depuis le blob git validé :
unités `foxchess-*.service|timer`, `/usr/local/sbin/foxchess-env-fetch.sh`, vhost nginx.
Ce qui s'installe **une fois, à la main, par root** : Stockfish, sudoers, base, dossiers, premier clone.

---

## 1. GitHub

1. Dépôt **public** `Foxugly/foxChess`, branche par défaut `main`.
2. Environnement `production` ; secrets : `AWS_DEPLOY_ROLE_ARN`, `EC2_INSTANCE_ID`.
3. Identifiant numérique du dépôt (pour la confiance OIDC) : `gh api repos/Foxugly/foxChess --jq .id`
   → à reporter dans `REPO_ID` de `deploy/iam-cloudshell.sh`.
4. Protection de `main` (checks requis : `tests`, `lint`, `pip-audit`, `codeql (python)`,
   `codeql (javascript-typescript)`) et secret Dependabot `DEPENDABOT_AUTOMERGE_TOKEN`
   (OPERATIONS.md §3.20).

## 1 bis. DNS

Route 53, zone `foxugly.com` : enregistrement `A` `foxchess` → `54.229.220.110`.
Le certificat `foxugly.com` est un joker (`*.foxugly.com`) : rien à émettre.

## 2. IAM (hors machine — jamais avec les clés root de la machine, §3.5)

Scripté dans **`deploy/iam-cloudshell.sh`** (AWS CloudShell, après avoir rempli `REPO_ID`) :
rôle `foxchess-deploy` (OIDC, les deux formes de `sub`), et extension de l'instruction
`SsmReadFleetAppConfig` du rôle d'instance `foxugly-fleet-ec2` avec `/foxchess/prod` et
`/foxchess/prod/*`. Affiche à la fin l'ARN à mettre dans `AWS_DEPLOY_ROLE_ARN`.

## 3. Stockfish et PostgreSQL (root, une fois)

```bash
apt-get install -y stockfish          # /usr/games/stockfish (Stockfish 16 sur Ubuntu 24.04)
/usr/games/stockfish <<< 'quit'       # démarre ?

openssl rand -base64 33 | tr -d '\n' > /root/foxchess-db-password && chmod 600 /root/foxchess-db-password
sudo -u postgres psql <<SQL
CREATE ROLE foxchess LOGIN PASSWORD '$(cat /root/foxchess-db-password)';
CREATE DATABASE foxchess OWNER foxchess;
\c foxchess
ALTER SCHEMA public OWNER TO foxchess;
SQL
```

La sauvegarde hebdomadaire (`fleet-db-backup.timer`, §3.23) prend la nouvelle base d'elle-même.

## 4. Paramètres SSM `/foxchess/prod/*`

Scripté dans **`deploy/ssm-cloudshell.sh`**. Noms nus (convention de la flotte).

| Paramètre | Type | Valeur |
|---|---|---|
| `SECRET_KEY` | SecureString | générée par le script |
| `ALLOWED_HOSTS` | String | `foxchess.foxugly.com` |
| `CSRF_TRUSTED_ORIGINS` | String | `https://foxchess.foxugly.com` |
| `DB_ENGINE` | String | `postgresql` |
| `DB_NAME` / `DB_USER` | String | `foxchess` |
| `DB_PASSWORD` | SecureString | celui de l'étape 3 |
| `DB_HOST` / `DB_PORT` | String | `127.0.0.1` / `5432` |
| `STOCKFISH_PATH` | String | `/usr/games/stockfish` |
| `SENTRY_DSN` | String | projet `foxchess-backend` (org `foxugly-srl`, de.sentry.io) |
| `SENTRY_ENVIRONMENT` | String | `production` |

Facultatifs : `STOCKFISH_THREADS` (1), `STOCKFISH_HASH_MB` (16), `RETENTION_PARTIES_JOURS` (30).

## 5. Machine (root, une fois)

```bash
install -d -o django -g www-data -m 750 /var/log/foxchess

# Premier clone et environnement, en django (§3.11 : amorçage)
sudo -u django bash -c 'umask 027; cd /var/www/django_websites && git clone https://github.com/Foxugly/foxChess.git'
sudo -u django bash -c 'cd /var/www/django_websites/foxChess && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt'

# Depuis le blob git validé, jamais par cp depuis l'arborescence de django (§3.10).
cd /var/www/django_websites/foxChess
G="git -c safe.directory=$PWD show HEAD:deploy"

$G/sudoers/foxchess-deploy > /tmp/foxchess-deploy && visudo -cf /tmp/foxchess-deploy && install -o root -g root -m 0440 /tmp/foxchess-deploy /etc/sudoers.d/foxchess-deploy
rm -f /tmp/foxchess-deploy; visudo -c

$G/nginx/foxchess.foxugly.com.conf > /etc/nginx/sites-available/foxchess.foxugly.com
ln -s /etc/nginx/sites-available/foxchess.foxugly.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

for u in foxchess-env-fetch.service foxchess-gunicorn.service foxchess-purge.service foxchess-purge.timer; do
  git -c safe.directory=$PWD show HEAD:deploy/$u > /etc/systemd/system/$u
done
git -c safe.directory=$PWD show HEAD:deploy/fetch-env-from-ssm.sh > /usr/local/sbin/foxchess-env-fetch.sh
chown root:root /usr/local/sbin/foxchess-env-fetch.sh && chmod 0755 /usr/local/sbin/foxchess-env-fetch.sh
systemctl daemon-reload
systemctl enable --now foxchess-env-fetch.service
sudo -u django bash deploy/ssm-deploy.sh      # migrate, collectstatic, restart
systemctl enable --now foxchess-gunicorn.service foxchess-purge.timer

# Un administrateur (e-mail seul, §3.16)
sudo -u django bash -c 'cd /var/www/django_websites/foxChess && set -a && . /run/foxchess/.env && .venv/bin/python manage.py createsuperuser'
```

Rotation d'un secret : `systemctl restart foxchess-env-fetch` **puis** `systemctl restart foxchess-gunicorn`.

## 6. Après la mise en service

- UptimeRobot : moniteur HTTPS sur `https://foxchess.foxugly.com/health/` (300 s, mot-clé `"ok"`).
  `/health/` vérifie la base **et** la présence de Stockfish.
- Sentry : projet `foxchess-backend`.
- `OPERATIONS.md` : ligne d'inventaire (§2), port 8012 pris (§3.4, prochain libre **8013**),
  ligne dans la table des rôles (§3.11) ; `~/.claude/CLAUDE.md` : ligne du tableau de la flotte.
- Vérifications §3.12 : `/health/` 200 ;
  `sudo find /var/www/django_websites/foxChess ! -type l \( -perm /020 -o -perm /004 \)` vide ;
  `sudo -l -U django` ne montre que les autorisations attendues ;
  `systemctl list-timers foxchess-purge.timer` planifié.

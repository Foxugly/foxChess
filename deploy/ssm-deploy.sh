#!/usr/bin/env bash
#
# foxChess — étape applicative du déploiement, lancée par SSM en tant que
# django (voir .github/workflows/deploy.yml), après le `git reset` sur
# origin/main et l'installation, par root, des unités et de nginx.
#
# Dépendances, migrations, fichiers statiques, redémarrage.
set -euo pipefail
umask 027

APP=/var/www/django_websites/foxChess
ENV_FILE=/run/foxchess/.env
cd "$APP"

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: $APP/.venv absent — faire d'abord l'amorçage (deploy/README.md)." >&2
  exit 1
fi

# requirements.txt est un verrou haché (généré par uv depuis requirements.in) :
# la production installe exactement les versions que la CI a testées. Sans
# verrou, `pip install -r` ne mettait jamais à jour une version déjà installée
# encore dans sa plage, et la box ratait les correctifs. --no-deps : tout est
# dans le verrou ; pip check vérifie qu'il est cohérent.
.venv/bin/pip install --quiet --require-hashes --no-deps -r requirements.txt
.venv/bin/pip check

if [ ! -s "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE absent ou vide — foxchess-env-fetch a-t-il tourné ? (systemctl status foxchess-env-fetch)" >&2
  exit 1
fi

# Lecture littérale (clé=valeur), jamais `source` : une valeur contenant $( )
# ou des guillemets ne doit pas être interprétée par le shell (§3.11).
while IFS='=' read -r cle valeur || [ -n "$cle" ]; do
  case "$cle" in ''|\#*) continue ;; esac
  export "$cle=$valeur"
done < "$ENV_FILE"

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput --verbosity 0
.venv/bin/python manage.py check --deploy --fail-level ERROR

sudo /bin/systemctl restart foxchess-gunicorn
echo "[ssm-deploy] foxChess $(git rev-parse --short HEAD) déployé."

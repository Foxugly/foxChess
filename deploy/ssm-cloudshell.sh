#!/usr/bin/env bash
# Paramètres SSM de foxChess (/foxchess/prod/*), à coller dans AWS CloudShell (eu-west-1).
#
# - SECRET_KEY est générée ici et n'est JAMAIS remplacée si elle existe déjà.
# - DB_PASSWORD est demandé sans écho : sur le serveur, `sudo cat /root/foxchess-db-password`.
# - Aucune valeur secrète n'est affichée ; la fin liste les noms et les types.
# Sentry (SENTRY_DSN, SENTRY_ENVIRONMENT) s'ajoute ensuite, avec le même put-parameter.
#
# Ré-exécutable : les paramètres non secrets sont réécrits à l'identique.
set -euo pipefail

REGION=eu-west-1
P=/foxchess/prod

put() {  # put <nom> <type> <valeur>
  aws ssm put-parameter --region "$REGION" --name "$P/$1" --type "$2" --value "$3" \
    --overwrite --no-cli-pager >/dev/null
  echo "  $P/$1 ($2)"
}

read -r -s -p "DB_PASSWORD (sortie de sudo cat /root/foxchess-db-password) : " DB_PASSWORD; echo
[ "${#DB_PASSWORD}" -ge 20 ] || { echo "Mot de passe trop court : mauvais copier-coller ?" >&2; exit 1; }

echo "Écriture :"
if aws ssm get-parameter --region "$REGION" --name "$P/SECRET_KEY" >/dev/null 2>&1; then
  echo "  $P/SECRET_KEY existe déjà : conservée"
else
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
  aws ssm put-parameter --region "$REGION" --name "$P/SECRET_KEY" --type SecureString \
    --value "$SECRET_KEY" --no-cli-pager >/dev/null
  unset SECRET_KEY
  echo "  $P/SECRET_KEY (SecureString, générée)"
fi
put DB_PASSWORD          SecureString "$DB_PASSWORD"; unset DB_PASSWORD
put ALLOWED_HOSTS        String "foxchess.foxugly.com"
put CSRF_TRUSTED_ORIGINS String "https://foxchess.foxugly.com"
put DB_ENGINE            String "postgresql"
put DB_NAME              String "foxchess"
put DB_USER              String "foxchess"
put DB_HOST              String "127.0.0.1"
put DB_PORT              String "5432"
put STOCKFISH_PATH       String "/usr/games/stockfish"

echo
echo "Contenu de $P (noms et types seulement) :"
aws ssm get-parameters-by-path --region "$REGION" --path "$P" --recursive \
  --query 'Parameters[].[Name,Type]' --output table --no-cli-pager

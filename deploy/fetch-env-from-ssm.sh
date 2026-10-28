#!/usr/bin/env bash
#
# foxChess — récupère la configuration depuis SSM Parameter Store vers /run.
#
# Repris de QuizOnline / Chronos (deploy/fetch-env-from-ssm.sh), même contrat :
# lancé au démarrage par foxchess-env-fetch.service (root, oneshot), il écrit
# /run/foxchess/.env (tmpfs : rien sur disque, rien dans un instantané EBS),
# atomiquement (fichier .tmp puis mv), et refuse de remplacer un .env valide
# par un fichier vide.
#
# Installé par le déploiement en /usr/local/sbin/foxchess-env-fetch.sh
# (root:root 0755), depuis le blob git validé — jamais exécuté depuis
# l'arborescence modifiable par django (OPERATIONS.md §3.10).
set -euo pipefail

PREFIX="${FOXCHESS_SSM_PREFIX:-/foxchess/prod}"
REGION="${FOXCHESS_SSM_REGION:-eu-west-1}"
OUT_DIR="${FOXCHESS_ENV_DIR:-/run/foxchess}"
OUT_FILE="${FOXCHESS_ENV_FILE:-$OUT_DIR/.env}"
OWNER="${FOXCHESS_ENV_OWNER:-django:www-data}"

echo "[fetch-env] prefix=$PREFIX region=$REGION out=$OUT_FILE"

mkdir -p "$OUT_DIR"
chmod 750 "$OUT_DIR"
chown root:www-data "$OUT_DIR"

TMP_FILE="$OUT_FILE.tmp"
: > "$TMP_FILE"
chmod 640 "$TMP_FILE"

OUT=$(aws ssm get-parameters-by-path \
  --region "$REGION" \
  --path "$PREFIX" \
  --recursive \
  --with-decryption \
  --output json)

python3 -c '
import json, sys
prefix, out_path, payload = sys.argv[1:4]
data = json.loads(payload)
n = 0
with open(out_path, "a", encoding="utf-8") as f:
    for p in data.get("Parameters", []):
        name = p["Name"]
        key = name[len(prefix) + 1:] if name.startswith(prefix + "/") else name.rsplit("/", 1)[-1]
        value = p["Value"]
        if "\n" in value or "\r" in value:
            print(f"ERROR: value of {key} contains a newline character", file=sys.stderr)
            sys.exit(2)
        f.write(f"{key}={value}\n")
        n += 1
print(f"[fetch-env] wrote {n} entries to staging file", file=sys.stderr)
' "$PREFIX" "$TMP_FILE" "$OUT"

COUNT=$(grep -c '=' "$TMP_FILE" || true)
if [ "$COUNT" -eq 0 ]; then
  echo "ERROR: no parameters found under $PREFIX — refusing to overwrite live .env" >&2
  rm -f "$TMP_FILE"
  exit 3
fi

chown "$OWNER" "$TMP_FILE"
chmod 640 "$TMP_FILE"
mv -f "$TMP_FILE" "$OUT_FILE"
echo "[fetch-env] $OUT_FILE ready ($COUNT entries, owner=$OWNER, mode=0640)"

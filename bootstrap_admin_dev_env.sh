#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE=".env"

random_key="$(
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"

tmp_file="$(mktemp)"
if [[ -f "$ENV_FILE" ]]; then
  INTERNAL_API_KEY_VALUE="$random_key" awk -F= '
    BEGIN {
      desired["APP_ENV"]="development"
      desired["ENABLE_ADMIN_AUTH"]="false"
      desired["INTERNAL_API_KEY"]=ENVIRON["INTERNAL_API_KEY_VALUE"]
    }
    /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/ {
      key=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      if (key in desired) {
        if (!(key in seen)) {
          print key "=" desired[key]
          seen[key]=1
        }
        next
      }
    }
    { print }
    END {
      for (i = 1; i <= 3; i++) {
        key = (i == 1 ? "APP_ENV" : (i == 2 ? "ENABLE_ADMIN_AUTH" : "INTERNAL_API_KEY"))
        if (!(key in seen)) {
          print key "=" desired[key]
        }
      }
    }
  ' "$ENV_FILE" > "$tmp_file"
else
  {
    echo "APP_ENV=development"
    echo "ENABLE_ADMIN_AUTH=false"
    echo "INTERNAL_API_KEY=$random_key"
  } > "$tmp_file"
fi

mv "$tmp_file" "$ENV_FILE"

echo "[OK] .env 已更新："
echo "APP_ENV=development"
echo "ENABLE_ADMIN_AUTH=false"
echo "INTERNAL_API_KEY=已更新（值不顯示）"

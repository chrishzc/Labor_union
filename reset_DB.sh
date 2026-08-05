#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "[ERROR] Missing project Python: $PWD/.venv/bin/python"
  exit 2
fi

PY="$PWD/.venv/bin/python"

if (($# == 0)); then
  echo "[Preview] This command rebuilds local union_db from the fixed v3 fixture."
  "$PY" -m scripts.reset_fake_database
  echo
  echo "[Warning] This will remove every current local client, order, staff, LINE and customer-service record."
  echo "          Use it only when you intentionally want to discard local working data."
  printf "Type union_db to confirm reset: "
  read -r confirmation
  if [[ "$confirmation" != "union_db" ]]; then
    echo "[Safe Stop] Reset cancelled."
    exit 0
  fi
  "$PY" -m scripts.reset_fake_database --apply --confirm-database union_db
else
  "$PY" -m scripts.reset_fake_database "$@"
fi

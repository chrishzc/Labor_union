#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "[ERROR] Missing project Python: $PWD/.venv/bin/python"
  exit 2
fi

PY="$PWD/.venv/bin/python"

if (($# == 0)); then
  echo "Resetting local union_db from the fixed v3 fixture..."
  "$PY" -m scripts.reset_fake_database --apply --confirm-database union_db
else
  "$PY" -m scripts.reset_fake_database "$@"
fi

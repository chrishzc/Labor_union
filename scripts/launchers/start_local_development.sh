#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
cd "$SCRIPT_DIR/../.."

if [[ "${1:-}" == "--dry-run" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PY="$PWD/.venv/bin/python"
  elif [[ -x .venv/Scripts/python.exe ]]; then
    PY="$PWD/.venv/Scripts/python.exe"
  else
    echo "Missing project virtual-environment Python."
    exit 1
  fi
  "$PY" -m scripts.launcher_preflight --profile local-unix
  exit $?
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv/bin/python. Create the development virtual environment first."
  exit 1
fi

PY="$PWD/.venv/bin/python"

choose_db_port() {
  if ! lsof -iTCP:3306 -sTCP:LISTEN >/dev/null 2>&1; then
    echo 3306
    return
  fi
  echo "Port 3306 is busy; using 3307 for local development." >&2
  echo 3307
}

DB_PORT="$(choose_db_port)"
docker compose up -d
"$PY" scripts/wait_for_db.py --port "$DB_PORT"
"$PY" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
"$PY" -m streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501 &
"$PY" -m scripts.run_line_worker &
"$PY" -m scripts.run_service_monitor &
"$PY" -m scripts.run_durable_job_worker &
"$PY" -m scripts.run_knowledge_worker &
"$PY" scripts/file_watcher.py &
wait

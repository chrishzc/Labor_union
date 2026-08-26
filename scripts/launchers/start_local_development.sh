#!/usr/bin/env bash
# File: start_local_development.sh
# Description: 驗證本機 DB readiness 後啟動 FastAPI、React/Vite、monitor 與 workers。
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
  "$PY" -m scripts.launcher_preflight --profile dual-run
  if [[ "${REACT_ADMIN_RUNTIME_PROFILE:-}" == "artifact-runtime" ]]; then
    "$PY" -m scripts.launcher_preflight --profile artifact-runtime
  fi
  exit $?
fi

if [[ "${1:-}" == "--smoke-test" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PY="$PWD/.venv/bin/python"
  elif [[ -x .venv/Scripts/python.exe ]]; then
    PY="$PWD/.venv/Scripts/python.exe"
  else
    echo "Missing project virtual-environment Python."
    exit 1
  fi
  exec "$PY" -m scripts.smoke_local_development_launcher
fi

if [[ "${1:-}" == "--artifact-runtime-smoke" ]]; then
  if [[ -x .venv/bin/python ]]; then PY="$PWD/.venv/bin/python"; else PY="$PWD/.venv/Scripts/python.exe"; fi
  exec "$PY" -m scripts.smoke_local_development_launcher --artifact-runtime
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv/bin/python. Create the development virtual environment first."
  exit 1
fi

PY="$PWD/.venv/bin/python"
export APP_ENV="${APP_ENV:-development}"
export INTERNAL_SERVICE_SHARED_KEY="${INTERNAL_SERVICE_SHARED_KEY:-$("${PY}" -c 'import secrets; print(secrets.token_urlsafe(32))')}"

if [[ "${REACT_ADMIN_RUNTIME_PROFILE:-}" == "artifact-runtime" ]]; then
  "$PY" -m scripts.launcher_preflight --profile artifact-runtime
fi

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
"$PY" -m scripts.update_local_database --require-current --database-port "$DB_PORT"
"$PY" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
if [[ "${REACT_ADMIN_RUNTIME_PROFILE:-}" == "artifact-runtime" ]]; then
  API_READY=0
  for _ in {1..30}; do
    if "$PY" -c 'from urllib.request import urlopen; raise SystemExit(0 if urlopen("http://127.0.0.1:8000/health", timeout=2).status == 200 else 1)' >/dev/null 2>&1; then
      API_READY=1
      break
    fi
    sleep 1
  done
  [[ "$API_READY" == "1" ]] || { echo "FastAPI did not become ready."; exit 1; }
  "$PY" -m scripts.run_service_monitor --react-admin-health-check
fi
(cd ui_react && npm run dev -- --host 0.0.0.0 --port 5173 --strictPort) &
if "$PY" -m scripts.launcher_preflight --profile line-worker >/dev/null 2>&1; then
  "$PY" -m scripts.run_line_worker &
else
  echo "Skipping LINE Worker: local LINE credentials or runtime configuration are unavailable."
fi
"$PY" -m scripts.run_service_monitor &
"$PY" -m scripts.run_durable_job_worker &
"$PY" -m scripts.run_incident_worker &
if grep -Eiq '^KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED=true$' .env 2>/dev/null; then
  "$PY" -m scripts.run_knowledge_worker &
fi
wait

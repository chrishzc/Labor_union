#!/usr/bin/env bash
# File: start_local_development.sh
# Description: 驗證本機 DB readiness 後啟動 FastAPI、React/Vite、monitor 與 workers。
set -euo pipefail

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
cd "$SCRIPT_DIR/../.."

# Docker Desktop on macOS can be installed without a global CLI symlink.
if ! command -v docker >/dev/null 2>&1 && [[ -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
fi

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
export MYSQL_CONTAINER="${MYSQL_CONTAINER:-mysql_db}"

if [[ "${REACT_ADMIN_RUNTIME_PROFILE:-}" == "artifact-runtime" ]]; then
  "$PY" -m scripts.launcher_preflight --profile artifact-runtime
fi

docker compose up -d redis
if [[ "$(docker inspect --format "{{.State.Running}}" "$MYSQL_CONTAINER" 2>/dev/null || true)" == "true" ]]; then
  echo "Reusing running MySQL container: $MYSQL_CONTAINER"
elif docker inspect "$MYSQL_CONTAINER" >/dev/null 2>&1; then
  docker start "$MYSQL_CONTAINER" >/dev/null
elif [[ "$MYSQL_CONTAINER" == "mysql_db" ]]; then
  docker compose up -d db
else
  echo "Configured MySQL container does not exist: $MYSQL_CONTAINER" >&2
  exit 1
fi
"$PY" scripts/wait_for_db.py
"$PY" -m scripts.update_local_database --require-current

set -m
OWNED_PIDS=()
OWNED_LABELS=()
LAST_OWNED_PID=""

start_owned() {
  local label="$1"
  shift
  "$@" &
  LAST_OWNED_PID=$!
  OWNED_PIDS+=("$LAST_OWNED_PID")
  OWNED_LABELS+=("$label")
}

register_owned() {
  LAST_OWNED_PID="$2"
  OWNED_LABELS+=("$1")
  OWNED_PIDS+=("$2")
}

cleanup_owned() {
  local status=$?
  trap - EXIT INT TERM
  local pid
  for pid in "${OWNED_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for pid in "${OWNED_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  exit "$status"
}

require_owned_process() {
  local label="$1"
  local pid="$2"
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "$label exited before readiness." >&2
    return 1
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  for _ in {1..30}; do
    if "$PY" -c 'from urllib.request import urlopen; import sys; raise SystemExit(0 if urlopen(sys.argv[1], timeout=2).status == 200 else 1)' "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "$label did not become ready." >&2
  return 1
}

trap cleanup_owned EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_owned "FastAPI" "$PY" -m uvicorn api.main:app --host 0.0.0.0 --port 8000
API_PID="$LAST_OWNED_PID"
wait_for_http "http://127.0.0.1:8000/health" "FastAPI"
if [[ "${REACT_ADMIN_RUNTIME_PROFILE:-}" == "artifact-runtime" ]]; then
  "$PY" -m scripts.run_service_monitor --react-admin-health-check
fi
(cd ui_react && exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort) &
register_owned "React/Vite" "$!"
REACT_PID="$LAST_OWNED_PID"
wait_for_http "http://127.0.0.1:5173/admin/" "React/Vite"
if "$PY" -m scripts.launcher_preflight --profile line-worker >/dev/null 2>&1; then
  start_owned "LINE Worker" "$PY" -m scripts.run_line_worker
  LINE_PID="$LAST_OWNED_PID"
else
  echo "Skipping LINE Worker: local LINE credentials or runtime configuration are unavailable."
fi
start_owned "Runtime Monitor" "$PY" -m scripts.run_service_monitor
MONITOR_PID="$LAST_OWNED_PID"
start_owned "Durable Background Worker" "$PY" -m scripts.run_durable_job_worker
DURABLE_PID="$LAST_OWNED_PID"
start_owned "Incident Maintenance Worker" "$PY" -m scripts.run_incident_worker
INCIDENT_PID="$LAST_OWNED_PID"
if grep -Eiq '^KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED=true$' .env 2>/dev/null; then
  start_owned "Knowledge Retrieval Worker" "$PY" -m scripts.run_knowledge_worker
  KNOWLEDGE_PID="$LAST_OWNED_PID"
fi

sleep 1
require_owned_process "FastAPI" "$API_PID"
require_owned_process "React/Vite" "$REACT_PID"
require_owned_process "Runtime Monitor" "$MONITOR_PID"
require_owned_process "Durable Background Worker" "$DURABLE_PID"
require_owned_process "Incident Maintenance Worker" "$INCIDENT_PID"
if [[ -n "${LINE_PID:-}" ]]; then require_owned_process "LINE Worker" "$LINE_PID"; fi
if [[ -n "${KNOWLEDGE_PID:-}" ]]; then require_owned_process "Knowledge Retrieval Worker" "$KNOWLEDGE_PID"; fi

while true; do
  for index in "${!OWNED_PIDS[@]}"; do
    pid="${OWNED_PIDS[$index]}"
    if ! kill -0 "$pid" 2>/dev/null; then
      set +e
      wait "$pid"
      status=$?
      set -e
      echo "${OWNED_LABELS[$index]} exited; stopping owned local runtime." >&2
      exit "$status"
    fi
  done
  sleep 2
done

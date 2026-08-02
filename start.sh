#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

echo "=========================================="
echo "Lobar Union System Development Startup Script"
echo "=========================================="

run_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

load_env() {
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
}

port_is_free() {
  "$PY" - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
PY
}

choose_db_port() {
  if [[ -n "${DB_PORT:-}" ]]; then
    export DB_PORT
    return
  fi

  for candidate in 3306 3307 3308 3309; do
    if port_is_free "$candidate"; then
      DB_PORT="$candidate"
      export DB_PORT
      if [[ "$candidate" != "3306" ]]; then
        echo "[Info] Port 3306 is busy; using DB_PORT=$candidate for this run."
      fi
      return
    fi
  done

  echo "[Error] No free MySQL port found in 3306-3309. Set DB_PORT in .env and retry."
  exit 1
}

echo "[Step 2] Setting Python environment..."
if [[ ! -x .venv/bin/python ]]; then
  echo "[Error] Virtual environment .venv not found. Please install dependencies first."
  echo "        建議先執行：python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
PY="$PWD/.venv/bin/python"

load_env
choose_db_port

echo "[Step 1] Launching Docker Compose (MySQL 8.0)..."
if ! run_docker_compose up -d; then
  echo "[Error] Failed to start Docker Compose! Please check if Docker Desktop is running."
  exit 1
fi

if [[ -z "${INTERNAL_API_KEY:-}" ]]; then
  INTERNAL_API_KEY="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  export INTERNAL_API_KEY
fi
echo "[Security] FastAPI and Streamlit share one internal API key for this run."

echo "[Step 3] Waiting for MySQL database to become ready..."
"$PY" scripts/wait_for_db.py

echo "[Step 4] Initializing database schema (schema.sql)..."
"$PY" scripts/init_db.py

echo "[Step 5] Generating roster and finance fake data (initial pass, schedule allocation will be skipped until data is imported)..."
"$PY" scripts/generate_fake_data.py

echo "[Step 6] Importing client HCM data..."
"$PY" scripts/imports/import_client_hcm.py

echo "[Step 7] Importing client BeClass data..."
"$PY" scripts/imports/import_client_beclass.py

echo "[Step 8] Importing caregiver BeClass data..."
"$PY" scripts/imports/import_staff_beclass.py

echo "[Step 9] Importing finance payment data..."
"$PY" scripts/imports/import_finance_excel.py

echo "[Step 10] Allocating caregiver schedules and diversifying order statuses..."
"$PY" scripts/generate_fake_data.py

echo "=========================================="
echo "Initialization and import completed successfully!"
echo "=========================================="

pids=()
cleanup() {
  if ((${#pids[@]})); then
    echo
    echo "[Stop] Shutting down services..."
    kill "${pids[@]}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[Step 11] Launching FastAPI server and ngrok..."
"$PY" start_fastapi_ngrok.py &
pids+=("$!")

echo "[Step 12] Launching Streamlit interface..."
"$PY" -m streamlit run ui/app.py &
pids+=("$!")

echo "=========================================="
echo "System is running!"
echo "- API Docs: http://127.0.0.1:8000/docs"
echo "- Streamlit UI: http://localhost:8501"
echo "按 Ctrl+C 停止所有服務。"
echo "=========================================="

wait

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

echo "=========================================="
echo "Lobar Union System Online Startup Script"
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
  echo "[Error] INTERNAL_API_KEY is missing. Configure it in .env before online startup."
  echo "        開發機可先執行：./bootstrap_admin_dev_env.sh"
  exit 1
fi

echo "[Step 3] Waiting for MySQL database to become ready..."
"$PY" scripts/wait_for_db.py

echo "=========================================="
echo "Database connection ready! Starting services..."
echo "=========================================="
echo "[Notice] ngrok is development-only and is not started by online.sh."
echo "[Notice] LINE public webhook access requires the Cloudflare Tunnel planned for Stage 5.2."

pids=()
cleanup() {
  if ((${#pids[@]})); then
    echo
    echo "[Stop] Shutting down services..."
    kill "${pids[@]}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[Step 4] Launching FastAPI server..."
"$PY" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
pids+=("$!")

echo "[Step 5] Launching Streamlit interface..."
"$PY" -m streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501 &
pids+=("$!")

echo "[Step 6] Launching File Watcher Service..."
"$PY" scripts/file_watcher.py &
pids+=("$!")

echo "=========================================="
echo "Lobar Union System online services are running!"
echo "- API Docs: http://127.0.0.1:8000/docs"
echo "- Streamlit UI: http://localhost:8501"
echo "- File Watcher: Monitoring downloads/ folder"
echo "按 Ctrl+C 停止所有服務。"
echo "=========================================="

wait

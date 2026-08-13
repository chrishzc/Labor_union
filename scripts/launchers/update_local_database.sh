#!/usr/bin/env bash
# File: update_local_database.sh
# Description: Upgrades the configured local database through a verified candidate.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

export PATH="/opt/homebrew/opt/mysql-client/bin:/usr/local/opt/mysql-client/bin:$PATH"

PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "[ERROR] Missing project Python: $PYTHON"
  exit 2
fi

if ! command -v mysql >/dev/null 2>&1 || ! command -v mysqldump >/dev/null 2>&1; then
  echo "[ERROR] Missing MySQL client commands: mysql and mysqldump."
  echo "Install them on macOS with:"
  echo "  brew install mysql-client"
  echo
  echo "If Homebrew says mysql-client is already installed, run:"
  echo "  export PATH=\"/opt/homebrew/opt/mysql-client/bin:\$PATH\""
  exit 2
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  "$PYTHON" -m scripts.launcher_preflight --profile database-update
  exit $?
fi

if [[ $# -gt 0 ]]; then
  "$PYTHON" -m scripts.update_local_database "$@"
  exit $?
fi

echo "Previewing preserve-data update for the database configured in .env..."
if ! "$PYTHON" -m scripts.update_local_database; then
  echo "[ERROR] Database update preflight failed. Review the reported schema state before retrying."
  exit 1
fi

echo
echo "Stop API, UI, monitor, and workers before continuing."
echo "A backup and verified candidate are created before the .env database is replaced under the same name."
read -r -p "Type UPDATE to continue: " UPDATE_CONFIRM
UPDATE_CONFIRM_UPPER="$(printf '%s' "$UPDATE_CONFIRM" | tr '[:lower:]' '[:upper:]')"
if [[ "$UPDATE_CONFIRM_UPPER" != "UPDATE" ]]; then
  echo "Cancelled. No database changes were requested."
  exit 0
fi

if "$PYTHON" -m scripts.update_local_database --apply --confirm-configured-database; then
  echo "Database update completed. Restart local services; the configured database now contains the verified upgraded data."
else
  UPDATE_EXIT=$?
  echo "[ERROR] Database update failed with exit code $UPDATE_EXIT."
  exit "$UPDATE_EXIT"
fi

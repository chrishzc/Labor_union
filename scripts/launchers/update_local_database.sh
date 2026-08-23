#!/usr/bin/env bash
# File: update_local_database.sh
# Description: Runs the fast qualified additive route; replacement is explicit.
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

if [[ "${1:-}" == "--dry-run" ]]; then
  "$PYTHON" -m scripts.launcher_preflight --profile database-update
  PREFLIGHT_EXIT=$?
  if [[ $PREFLIGHT_EXIT -ne 0 ]]; then exit $PREFLIGHT_EXIT; fi
  "$PYTHON" -m scripts.update_local_database --dry-run
  exit $?
fi

if [[ $# -gt 0 ]]; then
  "$PYTHON" -m scripts.update_local_database "$@"
  exit $?
fi

echo "Previewing the qualified local additive update for the database configured in .env..."
if ! "$PYTHON" -m scripts.update_local_database; then
  echo "[ERROR] Database update preflight failed. Review the reported schema state before retrying."
  exit 1
fi

echo
echo "The default apply is additive-only and does not create a candidate or replace the source."
echo "Use --strategy replacement --allow-long-run only for the separately approved long-running route."
read -r -p "Type UPDATE to continue: " UPDATE_CONFIRM
UPDATE_CONFIRM_UPPER="$(printf '%s' "$UPDATE_CONFIRM" | tr '[:lower:]' '[:upper:]')"
if [[ "$UPDATE_CONFIRM_UPPER" != "UPDATE" ]]; then
  echo "Cancelled. No database changes were requested."
  exit 0
fi

if "$PYTHON" -m scripts.update_local_database --apply --confirm-configured-database; then
  echo "Database additive update completed. Restart local services if the release requires it."
else
  UPDATE_EXIT=$?
  echo "[ERROR] Database update failed with exit code $UPDATE_EXIT."
  exit "$UPDATE_EXIT"
fi

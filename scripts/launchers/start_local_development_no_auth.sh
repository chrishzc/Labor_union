#!/usr/bin/env bash
# File: start_local_development_no_auth.sh
# Description: 設定本機免登入環境後，委派 Unix 標準開發啟動入口。
set -euo pipefail

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  LOCAL_PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
  LOCAL_PYTHON="$PROJECT_ROOT/.venv/Scripts/python.exe"
else
  echo "Missing project virtual-environment Python." >&2
  exit 1
fi
export APP_ENV=development
export ACCESS_CONTROL_PROFILE=local_bypass
export ENABLE_ADMIN_AUTH=false
export VITE_ACCESS_CONTROL_PROFILE=local_bypass
export ADMIN_ENTRY_TARGET_STATE_PATH="${ADMIN_ENTRY_TARGET_STATE_PATH:-/Users/Shared/Labor_union_runtime/admin-entry-targets.json}"
# The current-anomalies cursor codec needs a signing key even for read-only
# local-bypass queries.  Keep it process-only: inherit an explicit value when
# supplied, otherwise generate one in memory and never write it to .env/logs.
if [[ -z "${ANOMALY_ISSUE_IDENTITY_KEY_V1:-}" ]]; then
  ANOMALY_ISSUE_IDENTITY_KEY_V1="$("$LOCAL_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
export ANOMALY_ISSUE_IDENTITY_KEY_V1

if [[ "${1:-}" != "--dry-run" ]]; then
  ENTRY_TARGET_STATE_PARENT="${ADMIN_ENTRY_TARGET_STATE_PATH%/*}"
  mkdir -p "$ENTRY_TARGET_STATE_PARENT"
  if [[ -e "$ADMIN_ENTRY_TARGET_STATE_PATH" || -L "$ADMIN_ENTRY_TARGET_STATE_PATH" ]]; then
    "$LOCAL_PYTHON" -m scripts.provision_admin_entry_target_state attest \
      --state "$ADMIN_ENTRY_TARGET_STATE_PATH" >/dev/null
  else
    "$LOCAL_PYTHON" -m scripts.provision_admin_entry_target_state provision \
      --template "$PROJECT_ROOT/config/admin_entry_targets.initial.json" \
      --output "$ADMIN_ENTRY_TARGET_STATE_PATH" >/dev/null
  fi
fi

# Local no-auth always uses the Vite source runtime.  Do not inherit a
# partially configured immutable-artifact binding from .env or a parent shell.
export REACT_ADMIN_RUNTIME_PROFILE=source
export REACT_ADMIN_CURRENT_ARTIFACT_DIR=
export REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=
export REACT_ADMIN_ACTIVE_SELECTOR=

exec "$SCRIPT_DIR/start_local_development.sh" "$@"

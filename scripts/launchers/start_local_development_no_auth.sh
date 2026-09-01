#!/usr/bin/env bash
# File: start_local_development_no_auth.sh
# Description: 設定本機免登入環境後，委派 Unix 標準開發啟動入口。
set -euo pipefail

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export APP_ENV=development
export ACCESS_CONTROL_PROFILE=local_bypass
export ENABLE_ADMIN_AUTH=false
export VITE_ACCESS_CONTROL_PROFILE=local_bypass
# The current-anomalies cursor codec needs a signing key even for read-only
# local-bypass queries.  Keep it process-only: inherit an explicit value when
# supplied, otherwise generate one in memory and never write it to .env/logs.
if [[ -z "${ANOMALY_ISSUE_IDENTITY_KEY_V1:-}" ]]; then
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    ANOMALY_ISSUE_IDENTITY_KEY_V1="$("$PROJECT_ROOT/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  elif [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
    ANOMALY_ISSUE_IDENTITY_KEY_V1="$("$PROJECT_ROOT/.venv/Scripts/python.exe" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  else
    echo "Missing project virtual-environment Python." >&2
    exit 1
  fi
fi
export ANOMALY_ISSUE_IDENTITY_KEY_V1
# Local no-auth always uses the Vite source runtime.  Do not inherit a
# partially configured immutable-artifact binding from .env or a parent shell.
export REACT_ADMIN_RUNTIME_PROFILE=source
export REACT_ADMIN_CURRENT_ARTIFACT_DIR=
export REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=
export REACT_ADMIN_ACTIVE_SELECTOR=

exec "$SCRIPT_DIR/start_local_development.sh" "$@"

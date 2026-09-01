#!/usr/bin/env bash
# File: start_local_development_no_auth.sh
# Description: 設定本機免登入環境後，委派 Unix 標準開發啟動入口。
set -euo pipefail

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
export APP_ENV=development
export ACCESS_CONTROL_PROFILE=local_bypass
export ENABLE_ADMIN_AUTH=false
export VITE_ACCESS_CONTROL_PROFILE=local_bypass
# Local no-auth always uses the Vite source runtime.  Do not inherit a
# partially configured immutable-artifact binding from .env or a parent shell.
export REACT_ADMIN_RUNTIME_PROFILE=source
export REACT_ADMIN_CURRENT_ARTIFACT_DIR=
export REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=
export REACT_ADMIN_ACTIVE_SELECTOR=

exec "$SCRIPT_DIR/start_local_development.sh" "$@"

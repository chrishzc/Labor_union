#!/usr/bin/env bash
# NAS MySQL connection comes from the existing .env DB_* settings.
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
export APP_ENV=development
export RUNTIME_DATABASE_TARGET=nas
exec bash "$SCRIPT_DIR/start_local_development.sh" "$@"

#!/usr/bin/env bash
# Initialize an existing empty NAS union_db; no arguments performs read-only preflight.
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
cd "$SCRIPT_DIR/../.."
exec .venv/bin/python -m scripts.initialize_nas_schema "$@"

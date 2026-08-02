#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

./bootstrap_admin_dev_env.sh
exec ./online.sh

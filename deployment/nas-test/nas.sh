#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! docker compose version >/dev/null 2>&1; then
  echo 'Docker Compose v2 is required (docker compose). Do not substitute legacy v1.'
  exit 2
fi
compose() { docker compose "$@"; }
case "${1:-help}" in
  prepare)
    mkdir -p settings
    chmod 700 settings
    docker run --rm --network none --user 0:0 \
      -v "$(pwd)/settings:/settings" -v lu-nas-preview-app-data:/data \
      "${APP_IMAGE:-labor-union-nas-test:local}" python -m scripts.nas_test_runtime prepare
    ;;
  database) compose up -d db redis ;;
  admin) compose run --rm --no-deps api python -m scripts.nas_test_runtime bootstrap-admin ;;
  start) compose up -d api ;;
  status)
    compose ps
    ids="$(compose ps -q)"
    if [ -n "$ids" ]; then docker stats --no-stream $ids; fi
    ;;
  line-check) compose run --rm line-check ;;
  stop) compose stop ;;
  *) echo 'Usage: sh nas.sh prepare | database | admin | start | status | line-check | stop' ;;
esac

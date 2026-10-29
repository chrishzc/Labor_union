#!/bin/bash
# DSM manual maintenance task. Only an already stopped project's backup is upgraded.
set -Eeuo pipefail
umask 077
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$SCRIPT_DIR"
fail() { printf '{"status":"blocked","error_code":"%s"}\n' "$1"; exit 2; }
for tool in docker timeout flock tee mktemp; do command -v "$tool" >/dev/null || fail "missing_$tool"; done
[[ $(id -u) == 0 ]] || fail root_required
[[ -f .env && -f compose.yaml && -f update_nas_database.py ]] || fail missing_existing_deployment_or_upgrade_script
MODE=${1:-}; [[ $# -ge 1 ]] && shift
[[ "$MODE" == --prepare || "$MODE" == --switch || "$MODE" == --update ]] || fail choose_update_prepare_or_switch
BACKUP_DIR=''; RUN_ID=''; LIMIT=1200; IMAGE=chris23144638/cecec:nas-secure-20261027-r2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-dir) [[ $# -ge 2 ]] || fail missing_backup_path; BACKUP_DIR=$2; shift 2;;
        --run-id) [[ $# -ge 2 ]] || fail missing_run_id; RUN_ID=$2; shift 2;;
        --image) [[ $# -ge 2 ]] || fail missing_image; IMAGE=$2; shift 2;;
        --timeout-seconds) [[ $# -ge 2 ]] || fail missing_timeout; LIMIT=$2; shift 2;;
        *) fail unknown_argument;;
    esac
done
[[ "$IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$ ]] || fail invalid_image
[[ "$LIMIT" =~ ^[1-9][0-9]{2,4}$ ]] && (( LIMIT >= 360 && LIMIT <= 86400 )) || fail invalid_timeout
[[ "$MODE" == --switch || ( "$BACKUP_DIR" == /* && -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ) ]] || fail choose_completed_full_backup
[[ "$MODE" != --switch || "$RUN_ID" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || fail invalid_run_id
PROJECT=''; COUNT=0
while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%$'\r'}
    if [[ "$line" == COMPOSE_PROJECT_NAME=* ]]; then PROJECT=${line#*=}; COUNT=$((COUNT + 1)); fi
done < .env
if [[ "$PROJECT" == \"*\" || "$PROJECT" == \'*\' ]]; then PROJECT=${PROJECT:1:${#PROJECT}-2}; fi
[[ $COUNT == 1 && "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || fail invalid_project_name
exec 9> .database-upgrade.lock
flock -n 9 || fail upgrade_already_running
export DOCKER_HOST=unix:///var/run/docker.sock
docker image inspect "$IMAGE" --format '{{.Id}}' >/dev/null
run_phase() {
local phase=$1
local ARGS=(--project-dir "$SCRIPT_DIR" --script-path "$SCRIPT_DIR/update_nas_database.py" --image "$IMAGE" --upgrade-timeout "$((LIMIT - 300))")
local MOUNTS=(--mount "type=bind,source=$SCRIPT_DIR,target=/deployment"
        --mount "type=bind,source=$SCRIPT_DIR/update_nas_database.py,target=/opt/nas-upgrade.py,readonly"
        --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock)
if [[ "$phase" == prepare ]]; then
    BACKUP_DIR=$(cd -- "$BACKUP_DIR" && pwd -P)
    ARGS+=(--backup-dir "$BACKUP_DIR")
    MOUNTS+=(--mount "type=bind,source=$BACKUP_DIR,target=/backup,readonly")
else
    ARGS+=(--run-id "$RUN_ID")
fi
# This trusted, short-lived coordinator alone receives Docker maintenance access.
# It does not expose a port, mount application files, or start the original project.
timeout -s TERM -k 40 "$LIMIT" docker run --rm --pull never --network none --read-only \
    --memory 256m --security-opt no-new-privileges:true \
    --tmpfs /tmp:rw,nosuid,size=32m "${MOUNTS[@]}" \
    --entrypoint python "$IMAGE" /opt/nas-upgrade.py "$phase" "${ARGS[@]}"
}

if [[ "$MODE" != --update ]]; then
    run_phase "${MODE#--}"
    exit $?
fi

# One operator action; the same lock covers preparation, switch and activation.
C=(docker compose --ansi never --env-file "$SCRIPT_DIR/.env" -p "$PROJECT" -f "$SCRIPT_DIR/compose.yaml")
"${C[@]}" config --quiet
LOG=$(mktemp "${TMPDIR:-/tmp}/labor-union-upgrade.XXXXXX")
trap 'rm -f -- "$LOG"' EXIT
run_phase prepare | tee "$LOG"
MATCHES=0
while IFS= read -r line; do
    if [[ "$line" == *'"status": "prepared"'* && "$line" =~ \"run_id\":\ \"([0-9]{8}T[0-9]{6}Z)\" ]]; then
        RUN_ID=${BASH_REMATCH[1]}; MATCHES=$((MATCHES + 1))
    fi
done < "$LOG"
[[ $MATCHES == 1 ]] || fail prepared_run_id_missing
run_phase switch
"${C[@]}" config --quiet
if ! timeout -s TERM -k 20 300 "${C[@]}" up -d --no-build --pull never --wait --wait-timeout 240; then
    "${C[@]}" stop --timeout 30 >/dev/null 2>&1 || true
    fail startup_failed_new_and_original_volumes_retained
fi
printf '{"status":"updated","run_id":"%s","original_volume_retained":true}\n' "$RUN_ID"

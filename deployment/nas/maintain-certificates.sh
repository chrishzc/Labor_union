#!/bin/bash
# DSM-only host coordinator. No secrets in arguments or task output.
set -Eeuo pipefail
umask 077
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$SCRIPT_DIR"

fail() { printf '{"status":"blocked","error":"%s"}\n' "$1"; exit 2; }
for tool in docker timeout flock; do command -v "$tool" >/dev/null || fail "missing_$tool"; done
[[ $(id -u) == 0 ]] || fail root_required
[[ -f .env && -f compose.yaml && -f nas_certificate_maintenance.py ]] || fail missing_deployment_files

# .env is data, never shell code. Read only the two non-secret paths/names needed here.
env_value() {
    local key=$1 line value='' count=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line=${line%$'\r'}
        if [[ "$line" == "$key="* ]]; then
            value=${line#*=}; count=$((count + 1))
        fi
    done < .env
    [[ $count -le 1 ]] || fail duplicate_setting
    if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then value=${value:1:${#value}-2}; fi
    printf '%s' "$value"
}
PROJECT=$(env_value COMPOSE_PROJECT_NAME)
DATA_ROOT=$(env_value NAS_DATA_ROOT)
IMAGE=$(env_value NAS_IMAGE)
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || fail invalid_project
[[ -n "$IMAGE" ]] || fail missing_application_image
[[ "$DATA_ROOT" == /* && -d "$DATA_ROOT/app-data" ]] || fail invalid_data_root
STATE=$(env_value NAS_CERT_MAINTENANCE_ROOT)
STATE=${STATE:-./certificate-maintenance}
[[ "$STATE" == /* ]] || STATE="$SCRIPT_DIR/$STATE"
[[ -d "$STATE" && ! -L "$STATE" ]] || fail create_protected_maintenance_folder_first
for directory in app-data controlled-files line-media knowledge; do
    [[ "$(readlink -f "$STATE")/" != "$(readlink -f "$DATA_ROOT/$directory")/"* ]] || fail maintenance_inside_application_data
done
[[ $(stat -c '%u' "$STATE") == 0 ]] || fail maintenance_folder_must_be_root_owned
[[ $(stat -c '%a' "$STATE") == 700 ]] || fail maintenance_folder_requires_mode_700_and_DSM_ACL

if [[ ${1:-} != --run ]]; then
    [[ ${1:-} == --check || ${1:-} == --apply ]] || fail choose_check_or_apply
    # Bounds include coordinator recovery. A killed run leaves a resumable journal.
    exec timeout -s TERM -k 30 600 /bin/bash "$0" --run "$1"
fi
MODE=${2:-}
[[ "$MODE" == --check || "$MODE" == --apply ]] || fail invalid_mode
exec 9> "$STATE/task.lock"
flock -n 9 || fail maintenance_already_running
D=(docker --host unix:///var/run/docker.sock)
C=("${D[@]}" compose --project-directory "$SCRIPT_DIR" --env-file "$SCRIPT_DIR/.env" -p "$PROJECT" -f "$SCRIPT_DIR/compose.yaml")
bounded() { timeout -s TERM -k 5 45 "$@"; }

# External volumes must preexist and belong to this installation, never create replacements.
for volume in private-ca management-tls line-tls db-ca server-tls; do
    actual=$(bounded "${D[@]}" volume inspect --format '{{index .Labels "com.docker.compose.project"}}' "${PROJECT}_${volume}")
    [[ "$actual" == "$PROJECT" ]] || fail certificate_volume_owner_mismatch
done
for service in db management-api line-api cloudflared; do
    container="$PROJECT-$service-1"
    found=$(bounded "${D[@]}" ps -a --filter "name=^/$container$" --format '{{.Names}}')
    if [[ -n "$found" ]]; then
        actual=$(bounded "${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project"}}/{{index .Config.Labels "com.docker.compose.service"}}' "$container")
        [[ "$actual" == "$PROJECT/$service" ]] || fail container_owner_mismatch
    fi
done

helper() { bounded "${C[@]}" run --rm --no-deps -T certificate-maintenance "$@"; }
running() {
    local status
    status=$(bounded "${D[@]}" inspect --format '{{.State.Status}}' "$PROJECT-$1-1" 2>/dev/null) || return 1
    [[ "$status" == running || "$status" == restarting ]]
}
declare -A ACTIVE=()
for service in db management-api line-api cloudflared; do
    if running "$service"; then ACTIVE[$service]=1; else ACTIVE[$service]=0; fi
done

reload_db() {
    [[ ${ACTIVE[db]} == 1 ]] || return 0
    # Local socket maintenance; existing root password stays in a file/process memory.
    if ! bounded "${D[@]}" exec "$PROJECT-db-1" bash -c 'mysql --defaults-extra-file=<(printf "[client]\nuser=root\npassword=%s\n" "$(cat /run/mysql-secrets/root-password)") --protocol=SOCKET --connect-timeout=5 --execute="ALTER INSTANCE RELOAD TLS"' >/dev/null 2>&1; then return 1; fi
}
restart_service() {
    [[ ${ACTIVE[$1]} == 1 ]] || return 0
    if ! bounded "${D[@]}" restart --time 20 "$PROJECT-$1-1" >/dev/null 2>&1; then return 1; fi
}
probe_once() {
    local service=$1 peer=$2 serial=$3 uid=1000:1000
    [[ "$peer" != db ]] || uid=0:0
    bounded "${D[@]}" exec -i --user "$uid" "$PROJECT-$service-1" python - probe --service "$peer" --expected-serial "$serial" < nas_certificate_maintenance.py >/dev/null 2>&1
}
verify_live() {
    local service peer serial attempt ready
    for service in management-api line-api; do
        [[ ${ACTIVE[$service]} == 1 ]] || continue
        if [[ "$service" == management-api ]]; then peer=management; else peer=line; fi
        serial=$(helper serial --service "$peer")
        [[ "$serial" =~ ^[a-f0-9]+$ ]] || return 1
        ready=0
        for attempt in {1..12}; do
            if probe_once "$service" "$service" "$serial"; then ready=1; break; fi
            sleep 2
        done
        [[ $ready == 1 ]] || return 1
    done
    if [[ ${ACTIVE[db]} == 1 ]]; then
        # At least one API must verify a fresh DB TLS connection; no business writes.
        service=management-api
        [[ ${ACTIVE[$service]} == 1 ]] || service=line-api
        [[ ${ACTIVE[$service]} == 1 ]] || return 1
        serial=$(helper serial --service db)
        [[ "$serial" =~ ^[a-f0-9]+$ ]] || return 1
        probe_once "$service" db "$serial"
    fi
}
publish() {
    helper publish --apply
    # Separate unprivileged public-file writer: no signing keys, host-root writes or network.
    # Atomic replace does not follow a hostile final symlink in application-controlled data.
    bounded "${D[@]}" run --rm --pull never --network none --read-only --user 1000:1000 --memory 64m \
        --mount "type=bind,source=$STATE/public,target=/cas,readonly" \
        --mount "type=bind,source=$DATA_ROOT/app-data,target=/data" \
        --entrypoint python "$IMAGE" -c 'import os,tempfile; from pathlib import Path
for source,target in [("api-ca.pem","management-api-ca.crt"),("db-ca.pem","nas-ca.pem")]:
    fd,name=tempfile.mkstemp(prefix=".ca-public-",dir="/data")
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(Path("/cas",source).read_bytes()); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name,0o444); os.replace(name,Path("/data",target))
    finally:
        Path(name).unlink(missing_ok=True)'
}
on_failure() {
    trap - ERR TERM INT
    set +e
    printf '{"status":"failed","action":"attempting_certificate_recovery"}\n'
    if [[ -f "$STATE/pending.json" ]] && helper rollback --apply; then
        reload_db && restart_service management-api && restart_service line-api && restart_service cloudflared && verify_live && publish
        if [[ $? == 0 ]]; then
            printf '{"status":"failed","recovery":"verified_previous_certificates"}\n'
        else
            printf '{"status":"failed","recovery":"requires_administrator"}\n'
        fi
    else
        printf '{"status":"failed","recovery":"journal_preserved_resume_next_run_or_contact_administrator"}\n'
    fi
    # Even successful rollback must trigger DSM's abnormal-exit email.
    exit 2
}
trap on_failure ERR TERM INT
if [[ "$MODE" == --check ]]; then helper status; exit 0; fi
helper prepare --apply
if [[ ! -f "$STATE/pending.json" ]]; then exit 0; fi
helper trust --apply
# cloudflared caches its origin trust; refresh before switching the LINE leaf.
restart_service cloudflared
helper activate --apply
reload_db
restart_service management-api
restart_service line-api
verify_live
publish
helper commit --apply --verified
printf '{"status":"completed","scope":"certificates_only","business_data_changes":false}\n'

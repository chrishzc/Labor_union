#!/bin/bash
# DSM host task: project database only; no service lifecycle commands or pruning.
set -Eeuo pipefail
umask 077
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$SCRIPT_DIR"
fail() { printf '{"status":"failed","error":"%s"}\n' "$1"; exit 2; }
trap 'fail backup_incomplete_previous_backups_preserved' ERR TERM INT
for tool in docker timeout flock gzip sha256sum readlink stat; do
    command -v "$tool" >/dev/null || fail "missing_$tool"
done
[[ $(id -u) == 0 ]] || fail root_required
[[ -f .env ]] || fail missing_existing_env
BACKUP_DIR=''; MODE=''; LIMIT=3600
while [[ $# -gt 0 ]]; do
    case "$1" in
        --check|--backup) [[ -z "$MODE" ]] || fail duplicate_mode; MODE=$1; shift;;
        --backup-dir) [[ $# -ge 2 ]] || fail missing_backup_directory; BACKUP_DIR=$2; shift 2;;
        --timeout-seconds) [[ $# -ge 2 ]] || fail missing_timeout; LIMIT=$2; shift 2;;
        --bounded) BOUNDED=1; shift;;
        *) fail unknown_argument;;
    esac
done
[[ "$MODE" == --check || "$MODE" == --backup ]] || fail choose_check_or_backup
[[ "$LIMIT" =~ ^[1-9][0-9]{0,5}$ ]] || fail invalid_timeout
[[ "$BACKUP_DIR" == /* && -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ]] || fail create_protected_backup_folder_first
BACKUP_DIR=$(readlink -f -- "$BACKUP_DIR")
[[ $(stat -c '%u' "$BACKUP_DIR") == 0 && $(stat -c '%a' "$BACKUP_DIR") == 700 ]] || fail backup_folder_requires_root_700_and_DSM_ACL
[[ "$BACKUP_DIR/" != "$SCRIPT_DIR/"* ]] || fail backup_must_be_outside_deployment_folder
[[ "$SCRIPT_DIR/" != "$BACKUP_DIR/"* ]] || fail backup_must_not_contain_deployment_folder
if [[ ${BOUNDED:-0} != 1 ]]; then
    exec timeout -s TERM -k 10 "$LIMIT" /bin/bash "$0" --bounded "$MODE" --backup-dir "$BACKUP_DIR" --timeout-seconds "$LIMIT"
fi
exec 9> "$BACKUP_DIR/task.lock"
flock -n 9 || fail backup_already_running

# Only read the non-secret project name; do not source/eval .env.
PROJECT=''; COUNT=0
while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%$'\r'}
    if [[ "$line" == COMPOSE_PROJECT_NAME=* ]]; then PROJECT=${line#*=}; COUNT=$((COUNT + 1)); fi
done < .env
[[ $COUNT == 1 ]] || fail missing_or_duplicate_project_name
if [[ "$PROJECT" == \"*\" || "$PROJECT" == \'*\' ]]; then PROJECT=${PROJECT:1:${#PROJECT}-2}; fi
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]+$ ]] || fail invalid_project_name
D=(docker --host unix:///var/run/docker.sock)
bounded() { timeout -s TERM -k 5 30 "$@"; }
DB="$PROJECT-db-1"
STATE=$(bounded "${D[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Status}}' "$DB" 2>/dev/null)
[[ "$STATE" == "$PROJECT|db|running" ]] || fail database_not_running_or_wrong_owner
VOLUME=$(bounded "${D[@]}" volume inspect --format '{{index .Labels "com.docker.compose.project"}}' "${PROJECT}_mysql-data" 2>/dev/null)
[[ "$VOLUME" == "$PROJECT" ]] || fail database_volume_owner_mismatch
ACTUAL=$(bounded "${D[@]}" inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}' "$DB" 2>/dev/null)
[[ "$ACTUAL" == "${PROJECT}_mysql-data" ]] || fail database_volume_mismatch
IDS=$(bounded "${D[@]}" ps -aq --filter "label=com.docker.compose.project=$PROJECT")
[[ -n "$IDS" ]] || fail missing_project_containers
readarray -t CONTAINERS <<< "$IDS"
SOURCES=$(bounded "${D[@]}" inspect --format '{{range .Mounts}}{{println .Source}}{{end}}' "${CONTAINERS[@]}" 2>/dev/null)
while IFS= read -r source; do
    [[ -n "$source" ]] || continue
    source=$(readlink -f -- "$source")
    [[ "$BACKUP_DIR/" != "${source%/}/"* ]] || fail backup_exposed_to_application
    [[ "$source/" != "$BACKUP_DIR/"* ]] || fail backup_must_not_contain_application_data
done <<< "$SOURCES"

# The password is read only inside db and passed to MySQL via an anonymous FD.
# Never print driver stderr (it can contain SQL/customer values).
DB_SCRIPT=$(cat <<'DB_SCRIPT'
set -euo pipefail
export LC_ALL=C
[[ "$MYSQL_DATABASE" =~ ^[a-zA-Z0-9_]+$ ]] || exit 2
password=$(cat /run/mysql-secrets/root-password)
password=${password//\\/\\\\}; password=${password//\"/\\\"}
client() { printf '[client]\nuser=root\npassword="%s"\n' "$password"; }
if [[ "$1" == check ]]; then
    mysql --defaults-extra-file=<(client) --protocol=SOCKET --connect-timeout=10 --batch --skip-column-names --execute="
SELECT IF(COUNT(*) > 0 AND SUM(ENGINE <> 'InnoDB') = 0, 'INNODB_OK', 'UNSUPPORTED_TABLE_ENGINE')
FROM information_schema.TABLES WHERE TABLE_SCHEMA='$MYSQL_DATABASE' AND TABLE_TYPE='BASE TABLE';
SELECT CONCAT('database=', '$MYSQL_DATABASE');
SELECT CONCAT('mysql_version=', @@version);
SELECT CONCAT('base_tables=', COUNT(*)) FROM information_schema.TABLES WHERE TABLE_SCHEMA='$MYSQL_DATABASE' AND TABLE_TYPE='BASE TABLE';
SELECT CONCAT('routines=', COUNT(*)) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='$MYSQL_DATABASE';
SELECT CONCAT('triggers=', COUNT(*)) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='$MYSQL_DATABASE';
SELECT CONCAT('events=', COUNT(*)) FROM information_schema.EVENTS WHERE EVENT_SCHEMA='$MYSQL_DATABASE';"
elif [[ "$1" == dump ]]; then
    exec mysqldump --defaults-extra-file=<(client) --protocol=SOCKET \
        --single-transaction --quick --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF \
        --routines --events --triggers --hex-blob --default-character-set=utf8mb4 \
        --databases "$MYSQL_DATABASE"
else exit 2; fi
DB_SCRIPT
)
META=$(printf '%s\n' "$DB_SCRIPT" | bounded "${D[@]}" exec -i "$DB" bash -s -- check 2>/dev/null)
[[ "${META%%$'\n'*}" == INNODB_OK ]] || fail only_nonempty_InnoDB_databases_supported
if [[ "$MODE" == --check ]]; then
    printf '{"status":"ready","scope":"project_sql_only","services_stopped":false}\n'
    exit 0
fi
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FINAL="$BACKUP_DIR/$STAMP"
PART="$BACKUP_DIR/.partial-$STAMP"
[[ ! -e "$FINAL" && ! -e "$PART" ]] || fail backup_name_exists
mkdir -m 700 -- "$PART"
printf '%s\nproject=%s\nstarted_utc=%s\n' "$META" "$PROJECT" "$STAMP" > "$PART/metadata.txt"
# Streaming + gzip -1 avoids loading the database into NAS RAM.
printf '%s\n' "$DB_SCRIPT" | "${D[@]}" exec -i "$DB" timeout -s TERM -k 5 "$LIMIT" bash -s -- dump 2>/dev/null | gzip -1 > "$PART/database.sql.gz"
gzip -t "$PART/database.sql.gz"
gzip -dc "$PART/database.sql.gz" | tail -n 3 | grep -q '^-- Dump completed on '
(cd -- "$PART" && sha256sum database.sql.gz metadata.txt > SHA256SUMS && sha256sum -c SHA256SUMS >/dev/null)
printf 'SQL backup complete\n' > "$PART/COMPLETE"
mv -- "$PART" "$FINAL"
printf '{"status":"completed","scope":"project_sql_only","backup":"%s","retention":"permanent","services_stopped":false}\n' "$STAMP"

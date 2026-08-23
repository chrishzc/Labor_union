"""
File: runtime_monitor_repository.py
Description: 提供 runtime health 與 LINE alert target 的 MySQL projection、鎖與 receipt 存取。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from infrastructure.mysql.line_repository_support import aware_utc, database_utc
from subsystems.line.runtime_monitoring import (
    RuntimeHealthEvent,
    RuntimeHealthObservation,
    RuntimeHealthRecord,
    RuntimeHealthStatus,
)


class MySqlRuntimeMonitorRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def record_heartbeat(self, service_name, instance_id, process_id, host_name, status, details, now):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _UPSERT_SERVICE_HEARTBEAT,
                (service_name, instance_id, process_id, host_name, status,
                 json.dumps(details, ensure_ascii=False, separators=(",", ":")),
                 database_utc(now), database_utc(now),
                 database_utc(now) if status == "stopped" else None),
            )

    def record_observation(self, observation: RuntimeHealthObservation, failure_threshold=2, recovery_threshold=2):
        with self._connection.cursor() as cursor:
            cursor.execute(_LOCK_HEALTH, (observation.check_name,))
            previous = cursor.fetchone()
            prior_status = str(previous["health_status"]) if previous else None
            failures = int(previous["consecutive_failures"]) if previous else 0
            successes = int(previous["consecutive_successes"]) if previous else 0
            raw = observation.status.value
            if raw == RuntimeHealthStatus.HEALTHY.value:
                successes += 1
                failures = 0
                effective = raw if previous is None or successes >= recovery_threshold else prior_status
            elif raw in {RuntimeHealthStatus.WARNING.value, RuntimeHealthStatus.CRITICAL.value}:
                failures += 1
                successes = 0
                effective = raw if previous is None or failures >= failure_threshold else prior_status
            else:
                failures = successes = 0
                effective = raw
            effective = effective or raw
            changed = previous is None or effective != prior_status
            changed_at = observation.checked_at if changed else aware_utc(previous["status_changed_at_utc"])
            cursor.execute(
                _UPSERT_HEALTH,
                (observation.check_name, observation.component, effective, raw,
                 observation.message,
                 json.dumps(observation.details, ensure_ascii=False, separators=(",", ":")),
                 observation.response_ms, failures, successes,
                 database_utc(observation.checked_at),
                 database_utc(observation.checked_at) if raw == "healthy" else None,
                 database_utc(changed_at)),
            )
            if not changed:
                return None
            transition = _transition(prior_status, effective)
            cursor.execute(
                _INSERT_EVENT,
                (observation.check_name, observation.component, transition, prior_status,
                 effective, observation.message,
                 json.dumps(observation.details, ensure_ascii=False, separators=(",", ":")),
                 observation.fingerprint, database_utc(observation.checked_at)),
            )
            return int(cursor.lastrowid)

    def list_status(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_HEALTH)
            rows = cursor.fetchall() or ()
        return tuple(_health_record(row) for row in rows)

    def list_events(self, limit=100):
        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_EVENTS, (limit,))
            rows = cursor.fetchall() or ()
        return tuple(_health_event(row) for row in rows)

    def can_release(self, escalation: object) -> bool:
        """Require a later committed recovery for the exact LINE Worker event."""

        source_kind = _object_field(escalation, "source_kind")
        trigger_code = _object_field(escalation, "trigger_code")
        identity = _object_field(escalation, "source_event_identity")
        if source_kind != "runtime_health" or str(getattr(trigger_code, "value", trigger_code)) != "runtime_critical":
            return False
        if not isinstance(identity, str) or not identity:
            return False
        with self._connection.cursor() as cursor:
            cursor.execute(_LOCK_RUNTIME_CRITICAL_SOURCE, (identity,))
            source = cursor.fetchone()
            if source is None:
                return False
            if (
                str(source["check_name"]) != "line_worker"
                or str(source["component"]) != "LINE Worker"
                or str(source["resulting_status"]) != "critical"
            ):
                return False
            cursor.execute(
                _LOCK_LATER_RUNTIME_RECOVERY,
                (source["check_name"], source["component"], int(source["id"])),
            )
            return cursor.fetchone() is not None

    def upsert_group_target(self, group_id: str, display_name: str, actor_id: str) -> bool:
        raise RuntimeError("line_alert_target_legacy_upsert_retired")

    def add_admin_target(
        self,
        admin_user_id: int,
        minimum_status: str,
        actor_id: str,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_LINKED_ADMIN, (admin_user_id,))
            admin = cursor.fetchone()
            if admin is None:
                raise LookupError("line_alert_admin_not_linked")
            cursor.execute(
                _UPSERT_ADMIN_TARGET,
                (admin_user_id, admin["display_name"], minimum_status, actor_id),
            )
            cursor.execute(_ADMIN_TARGET_ID, (admin_user_id,))
            return int(cursor.fetchone()["id"])

    def list_targets(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_TARGETS)
            return tuple(cursor.fetchall() or ())

    def list_admin_alert_candidates(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_ADMIN_ALERT_CANDIDATES)
            return tuple(cursor.fetchall() or ())

    def list_alert_targets(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_ALERT_TARGETS)
            return tuple(cursor.fetchall() or ())

    def acquire_alert_target_lock(self, timeout_seconds: int) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(_GET_ALERT_TARGET_LOCK, (ALERT_TARGET_LOCK_NAME, timeout_seconds))
            row = cursor.fetchone()
        value = row.get("acquired") if hasattr(row, "get") else row[0]
        return int(value or 0) == 1

    def release_alert_target_lock(self) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(_RELEASE_ALERT_TARGET_LOCK, (ALERT_TARGET_LOCK_NAME,))
            row = cursor.fetchone()
        value = row.get("released") if hasattr(row, "get") else row[0]
        return int(value or 0) == 1

    def find_active_group_targets(self, *, for_update: bool):
        with self._connection.cursor() as cursor:
            cursor.execute(_ACTIVE_GROUP_TARGETS if for_update else _ACTIVE_GROUP_TARGETS_READ)
            return tuple(cursor.fetchall() or ())

    def find_group_target(self, group_id: str, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_TARGET_BY_ID + suffix, (group_id,))
            return cursor.fetchone()

    def get_alert_target(self, target_id: int, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_GET_ALERT_TARGET + suffix, (target_id,))
            return cursor.fetchone()

    def get_admin_target(self, admin_user_id: int, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_ADMIN_TARGET_BY_USER + suffix, (admin_user_id,))
            return cursor.fetchone()

    def insert_group_target(self, group_id: str, display_name: str, actor_id: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_INSERT_GROUP_TARGET, (group_id, display_name, actor_id))
            return int(cursor.lastrowid)

    def insert_admin_target(self, admin_user_id: int, minimum_status: str, actor_id: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_LINKED_ADMIN, (admin_user_id,))
            admin = cursor.fetchone()
            if admin is None:
                raise LookupError("line_alert_admin_not_linked")
            cursor.execute(
                _INSERT_ADMIN_TARGET,
                (admin_user_id, admin["display_name"], minimum_status, actor_id),
            )
            return int(cursor.lastrowid)

    def update_admin_target(self, target_id: int, minimum_status: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_UPDATE_ADMIN_TARGET, (minimum_status, target_id))

    def update_alert_target_enabled(self, target_id: int, enabled: bool) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_UPDATE_ALERT_TARGET_ENABLED, (enabled, target_id))
            if cursor.rowcount != 1:
                raise LookupError("line_alert_target_not_found")

    def load_admin_command_receipt(self, family: str, key: str, *, for_update: bool = True):
        with self._connection.cursor() as cursor:
            suffix = " FOR UPDATE" if for_update else ""
            cursor.execute(_ADMIN_RECEIPT_SELECT + suffix, (family, key))
            return cursor.fetchone()

    def save_admin_command_receipt(
        self, family: str, key: str, fingerprint: str, actor: str, reason: str, result: dict
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ADMIN_RECEIPT_INSERT,
                (family, key, fingerprint, fingerprint, actor, reason,
                 json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            )

    def save_alert_target_admin_audit(
        self, actor_id: str, action: str, resource_id: int, details: dict
    ) -> None:
        if not actor_id.startswith("admin:") or not actor_id[6:].isdigit():
            raise RuntimeError("line_alert_target_admin_actor_invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ADMIN_AUDIT_INSERT,
                (int(actor_id[6:]), action, str(resource_id),
                 json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            )

    def set_target_enabled(self, target_id: int, enabled: bool) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("UPDATE line_alert_notification_targets SET enabled=%s WHERE id=%s", (enabled, target_id))
            return cursor.rowcount == 1

    def pending_alert_targets(self, event_id: int):
        with self._connection.cursor() as cursor:
            cursor.execute(_PENDING_TARGETS, (event_id,))
            return tuple(cursor.fetchall() or ())

    def append_alert_intent(self, event_id, target_id, task_id, status, target_type, target_id_value, error_code=None):
        with self._connection.cursor() as cursor:
            cursor.execute(_INSERT_ALERT_INTENT, (event_id, target_id, task_id, status, target_type, target_id_value, error_code))


def _transition(before, after):
    if before is None or before in {"healthy", "unknown", "maintenance"} and after in {"warning", "critical"}:
        return "opened"
    if after == "healthy":
        return "recovered"
    if before == "warning" and after == "critical":
        return "escalated"
    return "test"


def _health_record(row):
    return RuntimeHealthRecord(str(row["check_name"]), str(row["component"]), str(row["health_status"]),
        str(row["raw_status"]), str(row["message"]), row.get("response_ms"),
        int(row["consecutive_failures"]), int(row["consecutive_successes"]),
        aware_utc(row["checked_at_utc"]), aware_utc(row["status_changed_at_utc"]),
        _json_object(row.get("details_snapshot")))


def _health_event(row):
    return RuntimeHealthEvent(int(row["id"]), str(row["check_name"]), str(row["component"]),
        str(row["transition_type"]), str(row["before_status"]) if row.get("before_status") else None,
        str(row["resulting_status"]), str(row["message"]), aware_utc(row["occurred_at_utc"]))


def _object_field(value, name):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


_UPSERT_SERVICE_HEARTBEAT = """INSERT INTO runtime_service_heartbeats
(service_name,instance_id,process_id,host_name,service_status,details_snapshot,started_at_utc,last_seen_at_utc,stopped_at_utc)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE process_id=VALUES(process_id),
host_name=VALUES(host_name),service_status=VALUES(service_status),details_snapshot=VALUES(details_snapshot),
last_seen_at_utc=VALUES(last_seen_at_utc),stopped_at_utc=VALUES(stopped_at_utc)"""
_LOCK_HEALTH = "SELECT health_status,consecutive_failures,consecutive_successes,status_changed_at_utc FROM runtime_health_status WHERE check_name=%s FOR UPDATE"
_UPSERT_HEALTH = """INSERT INTO runtime_health_status
(check_name,component,health_status,raw_status,message,details_snapshot,response_ms,consecutive_failures,consecutive_successes,checked_at_utc,last_success_at_utc,status_changed_at_utc)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE component=VALUES(component),health_status=VALUES(health_status),raw_status=VALUES(raw_status),message=VALUES(message),details_snapshot=VALUES(details_snapshot),response_ms=VALUES(response_ms),consecutive_failures=VALUES(consecutive_failures),consecutive_successes=VALUES(consecutive_successes),checked_at_utc=VALUES(checked_at_utc),last_success_at_utc=COALESCE(VALUES(last_success_at_utc),last_success_at_utc),status_changed_at_utc=VALUES(status_changed_at_utc)"""
_INSERT_EVENT = "INSERT INTO runtime_health_events (check_name,component,transition_type,before_status,resulting_status,message,details_snapshot,event_fingerprint,occurred_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
_LIST_HEALTH = "SELECT * FROM runtime_health_status ORDER BY component,check_name"
_LIST_EVENTS = "SELECT * FROM runtime_health_events ORDER BY occurred_at_utc DESC,id DESC LIMIT %s"
_LOCK_RUNTIME_CRITICAL_SOURCE = (
    "SELECT id,check_name,component,resulting_status FROM runtime_health_events "
    "WHERE event_fingerprint=%s FOR UPDATE"
)
_LOCK_LATER_RUNTIME_RECOVERY = (
    "SELECT id FROM runtime_health_events WHERE check_name=%s AND component=%s "
    "AND resulting_status='healthy' AND id>%s ORDER BY id LIMIT 1 FOR UPDATE"
)
_UPSERT_ADMIN_TARGET = """INSERT INTO line_alert_notification_targets
(target_type,admin_user_id,display_name,enabled,minimum_status,created_by_actor_id) VALUES ('admin_user',%s,%s,TRUE,%s,%s)
ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),minimum_status=VALUES(minimum_status),enabled=TRUE"""
_LIST_TARGETS = "SELECT id,target_type,admin_user_id,group_id,display_name,enabled,minimum_status,created_at_utc,updated_at_utc FROM line_alert_notification_targets ORDER BY id"
_LIST_ALERT_TARGETS = "SELECT id,target_type,display_name,enabled,minimum_status,updated_at_utc FROM line_alert_notification_targets ORDER BY id"
ALERT_TARGET_LOCK_NAME = "labor_union:line_alert_group_registration_v1"
_GET_ALERT_TARGET_LOCK = "SELECT GET_LOCK(%s,%s) AS acquired"
_RELEASE_ALERT_TARGET_LOCK = "SELECT RELEASE_LOCK(%s) AS released"
_TARGET_COLUMNS = "id,target_type,group_id,display_name,enabled,minimum_status,updated_at_utc"
_ACTIVE_GROUP_TARGETS = f"SELECT {_TARGET_COLUMNS} FROM line_alert_notification_targets WHERE target_type='group' AND enabled=TRUE FOR UPDATE"
_ACTIVE_GROUP_TARGETS_READ = f"SELECT {_TARGET_COLUMNS} FROM line_alert_notification_targets WHERE target_type='group' AND enabled=TRUE"
_GROUP_TARGET_BY_ID = f"SELECT {_TARGET_COLUMNS} FROM line_alert_notification_targets WHERE target_type='group' AND group_id=%s"
_GET_ALERT_TARGET = f"SELECT {_TARGET_COLUMNS} FROM line_alert_notification_targets WHERE id=%s"
_ADMIN_TARGET_BY_USER = f"SELECT {_TARGET_COLUMNS} FROM line_alert_notification_targets WHERE target_type='admin_user' AND admin_user_id=%s"
_INSERT_GROUP_TARGET = "INSERT INTO line_alert_notification_targets (target_type,group_id,display_name,enabled,minimum_status,created_by_actor_id) VALUES ('group',%s,%s,TRUE,'warning',%s)"
_INSERT_ADMIN_TARGET = "INSERT INTO line_alert_notification_targets (target_type,admin_user_id,display_name,enabled,minimum_status,created_by_actor_id) VALUES ('admin_user',%s,%s,TRUE,%s,%s)"
_UPDATE_ADMIN_TARGET = "UPDATE line_alert_notification_targets SET minimum_status=%s,enabled=TRUE WHERE id=%s"
_UPDATE_ALERT_TARGET_ENABLED = "UPDATE line_alert_notification_targets SET enabled=%s WHERE id=%s"
_ADMIN_RECEIPT_SELECT = "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s"
_ADMIN_RECEIPT_INSERT = "INSERT INTO admin_command_receipts (command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)"
_ADMIN_AUDIT_INSERT = """INSERT INTO admin_audit_logs
(admin_user_id,action,resource_type,resource_id,request_path,http_method,result_status,details_json)
VALUES (%s,%s,'line_alert_target',%s,'/api/v1/runtime/line-alert-targets','POST',200,%s)"""
_LIST_ADMIN_ALERT_CANDIDATES = """SELECT id,display_name,role,
(linked_line_user_id IS NOT NULL) AS line_linked FROM admin_users
WHERE enabled=TRUE AND linked_line_user_id IS NOT NULL ORDER BY display_name,id"""
_LINKED_ADMIN = """SELECT display_name FROM admin_users
WHERE id=%s AND enabled=TRUE AND linked_line_user_id IS NOT NULL"""
_ADMIN_TARGET_ID = """SELECT id FROM line_alert_notification_targets
WHERE target_type='admin_user' AND admin_user_id=%s"""
_PENDING_TARGETS = """SELECT t.id,t.target_type,t.group_id,t.minimum_status,a.linked_line_user_id,e.resulting_status,e.check_name,e.message,e.occurred_at_utc
FROM runtime_health_events e JOIN line_alert_notification_targets t ON t.enabled=TRUE
LEFT JOIN admin_users a ON a.id=t.admin_user_id
LEFT JOIN line_alert_delivery_intents i ON i.health_event_id=e.id AND i.target_id=t.id
WHERE e.id=%s AND i.id IS NULL"""
_INSERT_ALERT_INTENT = "INSERT INTO line_alert_delivery_intents (health_event_id,target_id,delivery_task_id,projection_status,resolved_line_target_type,resolved_line_target_id,error_code) VALUES (%s,%s,%s,%s,%s,%s,%s)"


def _json_object(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

__all__ = ["MySqlRuntimeMonitorRepository"]

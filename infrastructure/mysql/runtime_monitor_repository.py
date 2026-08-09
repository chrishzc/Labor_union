"""MySQL projections for active runtime monitoring and LINE alert targets."""

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

    def upsert_group_target(self, group_id: str, display_name: str, actor_id: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM line_alert_notification_targets WHERE group_id=%s", (group_id,))
            exists = cursor.fetchone() is not None
            cursor.execute(_UPSERT_GROUP_TARGET, (group_id, display_name, actor_id))
        return not exists

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
_UPSERT_GROUP_TARGET = """INSERT INTO line_alert_notification_targets
(target_type,group_id,display_name,enabled,minimum_status,created_by_actor_id) VALUES ('group',%s,%s,TRUE,'warning',%s)
ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),enabled=TRUE"""
_UPSERT_ADMIN_TARGET = """INSERT INTO line_alert_notification_targets
(target_type,admin_user_id,display_name,enabled,minimum_status,created_by_actor_id) VALUES ('admin_user',%s,%s,TRUE,%s,%s)
ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),minimum_status=VALUES(minimum_status),enabled=TRUE"""
_LIST_TARGETS = "SELECT id,target_type,admin_user_id,group_id,display_name,enabled,minimum_status,created_at_utc,updated_at_utc FROM line_alert_notification_targets ORDER BY id"
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

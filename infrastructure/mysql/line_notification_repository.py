"""
File: line_notification_repository.py
Description: 管理 LINE 通知意圖的可取消狀態，確保刪除規則不會讓舊任務穿透至 provider。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from infrastructure.mysql.line_repository_support import aware_utc
from domains.line.delivery import (
    LineDeliveryRequest,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineGroupId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.message_configuration import render_message_template
from subsystems.line.notification_policy import NotificationSourceEvent
from subsystems.line.notification_schedule import schedule_notification_occurrences
from subsystems.anomalies.line_notification_anomaly_projector import NotificationDecisionSource


class MySqlLineNotificationRepository:
    """Derived notification records only; owning domains retain their source facts."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def cancel_rule(self, rule_id: str, *, reason: str) -> int:
        """Cancel every unsent intent for one rule in the caller's outer UoW."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CANCEL_INTENTS_SQL,
                (reason, rule_id),
            )
            cancelled = int(cursor.rowcount)
            cursor.execute(_CANCEL_DELIVERY_TASKS_SQL, (reason, rule_id))
        return cancelled

    def mark_delivery_task_provider_accepted(self, delivery_task_id: int) -> None:
        """Keep derived intent state aligned once LINE accepted its linked task."""
        with self._connection.cursor() as cursor:
            cursor.execute(_MARK_PROVIDER_ACCEPTED_SQL, (delivery_task_id,))

    def cancel_service_day_log_reminders(
        self, assignment_id: int, service_date: str
    ) -> int:
        """Stop only unsent reminders for the exact completed assignment and service day."""
        if assignment_id <= 0 or not service_date:
            raise ValueError("service-day notification cancellation target is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CANCEL_SERVICE_DAY_INTENTS_SQL,
                (assignment_id, service_date),
            )
            cancelled = int(cursor.rowcount)
            cursor.execute(
                _CANCEL_SERVICE_DAY_TASKS_SQL,
                (assignment_id, service_date),
            )
        return cancelled

    def cancel_service_day_log_reminders_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> int:
        """Cancel only tasks derived from explicitly superseded Scheduling assignments."""
        normalized = tuple(sorted({int(value) for value in assignment_ids}))
        if not normalized or any(value <= 0 for value in normalized):
            raise ValueError("scheduling notification cancellation target is invalid")
        placeholders = ",".join("%s" for _ in normalized)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _cancel_service_day_assignment_intents_sql(placeholders), normalized
            )
            cancelled = int(cursor.rowcount)
            cursor.execute(
                _cancel_service_day_assignment_tasks_sql(placeholders), normalized
            )
        return cancelled

    def list_case_timeline(self, case_no: str) -> tuple[dict[str, object], ...]:
        """Return deidentified evidence only; notification payload text never crosses this API."""
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_TIMELINE_SQL, (case_no,))
            rows = tuple(cursor.fetchall() or ())
        return tuple(_timeline_row(row) for row in rows if isinstance(row, dict))

    def list_anomaly_sources(self, *, limit: int = 100) -> tuple[NotificationDecisionSource, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_NOTIFICATION_ANOMALY_SOURCES_SQL, (limit,))
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            NotificationDecisionSource(int(row["decision_id"]), str(row["source_event_identity"]),
                str(row["case_no"]), str(row["reason_code"]), int(row["source_version"]))
            for row in rows
            if isinstance(row, dict) and row.get("case_no")
        )

    def list_sources_without_decisions(
        self, *, limit: int = 100
    ) -> tuple[NotificationSourceEvent, ...]:
        """Return only configured source kinds whose committed event has no terminal decision."""
        if limit <= 0:
            raise ValueError("notification reconciliation limit is invalid")
        snapshot = self._current_configuration("notification_rules")
        if snapshot is None:
            return ()
        rules = snapshot[1].get("rules")
        event_codes = tuple(sorted({
            str(rule.get("event_code"))
            for rule in rules
            if isinstance(rule, dict) and isinstance(rule.get("event_code"), str)
        })) if isinstance(rules, list) else ()
        if not event_codes:
            return ()
        placeholders = ",".join("%s" for _ in event_codes)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _sources_without_decisions_sql(placeholders),
                (*event_codes, limit),
            )
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            _source_event_from_row(row)
            for row in rows
            if isinstance(row, dict)
        )

    def preview_manual_replay(self, source_event_id: int) -> dict[str, object]:
        source = self._source_event(source_event_id)
        if source is None:
            raise LookupError("notification source event not found")
        snapshot = self._current_configuration("notification_rules")
        rules = [] if snapshot is None else snapshot[1].get("rules", [])
        matching = sum(
            1 for rule in rules
            if isinstance(rule, dict) and rule.get("event_code") == source.event_code
        ) if isinstance(rules, list) else 0
        return {
            "source_event_id": source_event_id,
            "event_code": source.event_code,
            "historical_silent": source.historical_silent,
            "matching_rule_count": matching,
            "will_create_new_immutable_source": True,
        }

    def manual_replay_source(
        self, source_event_id: int, replay_identity: str, occurred_at: datetime
    ) -> int:
        source = self._source_event(source_event_id)
        if source is None:
            raise LookupError("notification source event not found")
        replay = NotificationSourceEvent(
            identity=replay_identity,
            event_code=source.event_code,
            historical_silent=False,
            facts=source.facts,
            source_domain="manual_replay",
            source_aggregate_type=source.source_aggregate_type,
            source_aggregate_identity=source.source_aggregate_identity,
            source_version=source.source_version,
            occurred_at=occurred_at,
        )
        return self.register_and_project(replay)

    def _source_event(self, source_event_id: int) -> NotificationSourceEvent | None:
        if source_event_id <= 0:
            raise ValueError("notification source event ID is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_SOURCE_EVENT_BY_ID_SQL, (source_event_id,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        return _source_event_from_row(row)

    def register_source_event(self, event: NotificationSourceEvent) -> int:
        """Persist an immutable owner-event copy; exact replay returns its prior ID."""
        if event.occurred_at is None:
            raise ValueError("notification source event requires occurred_at")
        facts_json = _canonical_json(event.facts)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _SOURCE_EVENT_INSERT_SQL,
                (
                    event.source_domain,
                    event.event_code,
                    event.identity,
                    event.source_aggregate_type,
                    event.source_aggregate_identity,
                    event.source_version,
                    event.historical_silent,
                    facts_json,
                    event.occurred_at,
                ),
            )
            if cursor.rowcount == 1:
                return int(cursor.lastrowid)
            cursor.execute(
                _SOURCE_EVENT_EXISTING_SQL,
                (event.source_domain, event.event_code, event.identity),
            )
            row = cursor.fetchone()
        if not isinstance(row, dict):
            raise RuntimeError("line_notification_source_event_duplicate_missing")
        actual = (
            str(row["source_aggregate_type"]),
            str(row["source_aggregate_identity"]),
            int(row["source_version"]),
            bool(row["historical_silent"]),
            _canonical_json(_json_object(row["facts_snapshot"])),
        )
        expected = (
            event.source_aggregate_type,
            event.source_aggregate_identity,
            event.source_version,
            event.historical_silent,
            facts_json,
        )
        if actual != expected:
            raise RuntimeError("line_notification_source_event_conflict")
        return int(row["id"])

    def register_and_project(self, event: NotificationSourceEvent) -> int:
        """Persist then atomically create only the tasks allowed by the active rule revision."""
        source_event_id = self.register_source_event(event)
        rule_snapshot = self._current_configuration("notification_rules")
        template_snapshot = self._current_configuration("message_templates")
        if rule_snapshot is None or template_snapshot is None:
            return source_event_id
        rule_revision_id, definition = rule_snapshot
        _, templates = template_snapshot
        rules = definition.get("rules")
        if not isinstance(rules, list):
            return source_event_id
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("event_code") != event.event_code:
                continue
            self._project_rule(
                source_event_id, event, rule_revision_id, rule, templates, template_snapshot[0]
            )
        return source_event_id

    def _project_rule(
        self,
        source_event_id: int,
        event: NotificationSourceEvent,
        rule_revision_id: int,
        rule: dict[str, object],
        templates: dict[str, object],
        template_revision_id: int,
    ) -> None:
        rule_id = rule.get("id")
        selector = rule.get("recipient_selector")
        if not isinstance(rule_id, str) or not isinstance(selector, str):
            return
        if event.historical_silent:
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "historical_source_silent", event)
            return
        if rule.get("enabled", False) is not True:
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "rule_shadow_mode", event)
            return
        if not _predicates_match(rule.get("predicates"), event.facts):
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "prerequisite_not_satisfied", event)
            return
        recipient = self._resolve_recipient(selector, event.facts)
        if recipient is None:
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "recipient_unavailable", event)
            return
        try:
            rendered = render_message_template(
                templates, str(rule["template_id"]), _template_variables(event.facts)
            )
            occurrences = schedule_notification_occurrences(
                occurred_at=event.occurred_at,
                schedule=_object(rule.get("schedule")),
                frequency=_object(rule.get("frequency"), default={"kind": "once"}),
            )
        except (KeyError, ValueError):
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, recipient, "suppressed", "template_or_schedule_invalid", event)
            return
        decision_id = self._record_decision(
            source_event_id, rule_revision_id, rule_id, selector, recipient, "intent_created", "rule_matched", event
        )
        for occurrence in occurrences:
            self._create_intent_if_absent(
                decision_id, occurrence.number, occurrence.scheduled_at, template_revision_id,
                str(rule["template_id"]), rendered, recipient, event,
            )

    def _current_configuration(self, kind: str) -> tuple[int, dict[str, object]] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_CURRENT_CONFIGURATION_SQL, (kind,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        definition = _json_object(row["definition_snapshot"])
        return int(row["revision_id"]), definition

    def _resolve_recipient(self, selector: str, facts: Any):
        if selector != "case_group" or not isinstance(facts, dict):
            return None
        case_no = facts.get("case_no")
        if not isinstance(case_no, str) or not case_no:
            return None
        with self._connection.cursor() as cursor:
            cursor.execute(_ACTIVE_CASE_GROUP_SQL, (case_no,))
            row = cursor.fetchone()
        if not isinstance(row, dict) or not isinstance(row.get("group_id"), str):
            return None
        return LineRecipient(LineRecipientType.GROUP, LineGroupId(row["group_id"]))

    def _record_decision(self, source_event_id, revision_id, rule_id, selector, recipient, status, reason, event) -> int:
        recipient_type = None if recipient is None else recipient.recipient_type.value
        recipient_identity = "" if recipient is None else recipient.identity.value
        snapshot = _canonical_json({"event_code": event.event_code, "facts": event.facts, "reason_code": reason})
        with self._connection.cursor() as cursor:
            cursor.execute(_DECISION_INSERT_SQL, (source_event_id, revision_id, rule_id, selector, recipient_type, recipient_identity, status, reason, snapshot))
            return int(cursor.lastrowid)

    def _create_intent_if_absent(self, decision_id, occurrence_number, scheduled_at, template_revision_id, template_id, rendered, recipient, event) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_INTENT_INSERT_SQL, (decision_id, occurrence_number, template_revision_id, template_id, rendered.payload_json, rendered.payload_json, scheduled_at))
            if cursor.rowcount != 1:
                return
            intent_id = int(cursor.lastrowid)
        from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository

        delivery = MySqlLineDeliveryTaskRepository(self._connection).enqueue(
            LineDeliveryRequest(recipient, rendered.message_kind, rendered.payload_json, scheduled_at,
                IdempotencyKey(f"line-notification:{decision_id}:{occurrence_number}"),
                CorrelationId(f"line-notification:{event.identity}"), event.source_aggregate_type, event.source_aggregate_identity)
        )
        with self._connection.cursor() as cursor:
            cursor.execute(_INTENT_TASK_LINK_SQL, (delivery.task_id.value, intent_id))
            if cursor.rowcount != 1:
                raise RuntimeError("line_notification_intent_task_link_conflict")


_CANCEL_INTENTS_SQL = (
    "UPDATE line_notification_intents AS intent "
    "JOIN line_notification_decisions AS decision ON decision.id=intent.decision_id "
    "SET intent.intent_status='cancelled',intent.cancellation_reason=%s,"
    "intent.cancelled_at_utc=UTC_TIMESTAMP(6) "
    "WHERE decision.rule_id=%s AND intent.intent_status='scheduled'"
)
_MARK_PROVIDER_ACCEPTED_SQL = (
    "UPDATE line_notification_intents SET intent_status='provider_accepted' "
    "WHERE delivery_task_id=%s AND intent_status='scheduled'"
)
_CANCEL_SERVICE_DAY_INTENTS_SQL = (
    "UPDATE line_notification_intents intent "
    "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
    "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
    "SET intent.intent_status='cancelled',intent.cancellation_reason='service_day_log_completed',"
    "intent.cancelled_at_utc=UTC_TIMESTAMP(6) "
    "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='scheduled' "
    "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED)=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.service_date'))=%s"
)
_CANCEL_SERVICE_DAY_TASKS_SQL = (
    "UPDATE line_delivery_tasks task "
    "JOIN line_notification_intents intent ON intent.delivery_task_id=task.id "
    "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
    "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
    "SET task.processing_status='cancelled',task.error_code='service_day_log_completed',"
    "task.error_message='service day log completed',task.lease_owner=NULL,"
    "task.lease_acquired_at_utc=NULL,task.lease_expires_at_utc=NULL "
    "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='cancelled' "
    "AND task.processing_status IN ('pending','retryable_failed','processing') "
    "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED)=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.service_date'))=%s"
)


def _cancel_service_day_assignment_intents_sql(placeholders: str) -> str:
    return (
        "UPDATE line_notification_intents intent "
        "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
        "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
        "SET intent.intent_status='cancelled',intent.cancellation_reason='assignment_replaced',"
        "intent.cancelled_at_utc=UTC_TIMESTAMP(6) "
        "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='scheduled' "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED) "
        f"IN ({placeholders})"
    )


def _cancel_service_day_assignment_tasks_sql(placeholders: str) -> str:
    return (
        "UPDATE line_delivery_tasks task "
        "JOIN line_notification_intents intent ON intent.delivery_task_id=task.id "
        "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
        "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
        "SET task.processing_status='cancelled',task.error_code='assignment_replaced',"
        "task.error_message='service assignment replaced',task.lease_owner=NULL,"
        "task.lease_acquired_at_utc=NULL,task.lease_expires_at_utc=NULL "
        "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='cancelled' "
        "AND task.processing_status IN ('pending','retryable_failed','processing') "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED) "
        f"IN ({placeholders})"
    )

_SOURCE_EVENT_INSERT_SQL = (
    "INSERT INTO line_notification_source_events (source_domain,event_code,"
    "source_event_identity,source_aggregate_type,source_aggregate_identity,"
    "source_version,historical_silent,facts_snapshot,occurred_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)"
)
_SOURCE_EVENT_EXISTING_SQL = (
    "SELECT id,source_aggregate_type,source_aggregate_identity,source_version,"
    "historical_silent,facts_snapshot FROM line_notification_source_events "
    "WHERE source_domain=%s AND event_code=%s AND source_event_identity=%s"
)
_SOURCE_EVENT_BY_ID_SQL = (
    "SELECT source_domain,event_code,source_event_identity,source_aggregate_type,"
    "source_aggregate_identity,source_version,historical_silent,facts_snapshot,occurred_at_utc "
    "FROM line_notification_source_events WHERE id=%s FOR UPDATE"
)
_CURRENT_CONFIGURATION_SQL = (
    "SELECT config_current.revision_id,revision.definition_snapshot "
    "FROM line_configuration_current config_current JOIN line_configuration_revisions revision "
    "ON revision.id=config_current.revision_id WHERE config_current.configuration_kind=%s"
)
_ACTIVE_CASE_GROUP_SQL = (
    "SELECT binding.group_id FROM line_order_group_bindings binding "
    "WHERE binding.case_no=%s AND binding.binding_status='active' AND binding.group_id IS NOT NULL "
    "AND EXISTS (SELECT 1 FROM line_order_group_participants customer "
    "WHERE customer.case_no=binding.case_no AND customer.participant_type='customer' AND customer.invitation_status='joined') "
    "AND EXISTS (SELECT 1 FROM line_order_group_participants staff "
    "WHERE staff.case_no=binding.case_no AND staff.participant_type='staff' AND staff.invitation_status='joined') "
    "FOR UPDATE"
)
_DECISION_INSERT_SQL = (
    "INSERT INTO line_notification_decisions (source_event_id,rule_revision_id,rule_id,recipient_selector,recipient_type,recipient_identity,decision_status,reason_code,decision_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)"
)
_INTENT_INSERT_SQL = (
    "INSERT IGNORE INTO line_notification_intents (decision_id,occurrence_number,template_revision_id,template_id,payload_snapshot,payload_fingerprint,scheduled_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,SHA2(%s,256),%s)"
)
_INTENT_TASK_LINK_SQL = (
    "UPDATE line_notification_intents SET delivery_task_id=%s WHERE id=%s AND delivery_task_id IS NULL"
)
_CASE_TIMELINE_SQL = (
    "SELECT source.id AS source_event_id,source.event_code,source.occurred_at_utc,source.historical_silent,"
    "decision.rule_id,decision.decision_status,decision.reason_code,decision.recipient_type,decision.recipient_identity,"
    "intent.occurrence_number,intent.intent_status,intent.scheduled_at_utc,intent.delivery_task_id,task.processing_status "
    "FROM line_notification_source_events source "
    "LEFT JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
    "LEFT JOIN line_notification_intents intent ON intent.decision_id=decision.id "
    "LEFT JOIN line_delivery_tasks task ON task.id=intent.delivery_task_id "
    "WHERE JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no'))=%s "
    "ORDER BY source.occurred_at_utc DESC,source.id DESC,decision.id DESC,intent.occurrence_number ASC"
)
_NOTIFICATION_ANOMALY_SOURCES_SQL = (
    "SELECT decision.id AS decision_id,source.source_event_identity,"
    "JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no')) AS case_no,"
    "decision.reason_code,source.source_version "
    "FROM line_notification_decisions decision JOIN line_notification_source_events source "
    "ON source.id=decision.source_event_id "
    "WHERE decision.reason_code IN ('recipient_unavailable','template_or_schedule_invalid') "
    "ORDER BY decision.id LIMIT %s"
)


def _sources_without_decisions_sql(placeholders: str) -> str:
    return (
        "SELECT source.source_domain,source.event_code,source.source_event_identity,"
        "source.source_aggregate_type,source.source_aggregate_identity,source.source_version,"
        "source.historical_silent,source.facts_snapshot,source.occurred_at_utc "
        "FROM line_notification_source_events source "
        "LEFT JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
        f"WHERE source.event_code IN ({placeholders}) AND decision.id IS NULL "
        "ORDER BY source.id LIMIT %s"
    )


def _canonical_json(value: object) -> str:
    if not isinstance(value, dict):
        value = dict(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise RuntimeError("line_notification_source_event_facts_invalid")
    return parsed


def _source_event_from_row(row: dict[str, object]) -> NotificationSourceEvent:
    return NotificationSourceEvent(
        identity=str(row["source_event_identity"]),
        event_code=str(row["event_code"]),
        historical_silent=bool(row["historical_silent"]),
        facts=_json_object(row["facts_snapshot"]),
        source_domain=str(row["source_domain"]),
        source_aggregate_type=str(row["source_aggregate_type"]),
        source_aggregate_identity=str(row["source_aggregate_identity"]),
        source_version=int(row["source_version"]),
        occurred_at=aware_utc(row["occurred_at_utc"]),
    )


def _object(value: object, *, default: dict[str, object] | None = None) -> dict[str, object]:
    if value is None and default is not None:
        return default
    if not isinstance(value, dict):
        raise ValueError("notification rule object is invalid")
    return value


def _predicates_match(predicates: object, facts: object) -> bool:
    if not isinstance(predicates, list) or not isinstance(facts, dict):
        return False
    checks = {
        "requires_cooking_true": facts.get("requires_cooking") is True,
        "baby_log_missing": facts.get("baby_log_completed") is False,
        "beclass_missing": facts.get("beclass_completed") is False,
    }
    return all(checks.get(item, False) for item in predicates)


def _template_variables(facts: object) -> dict[str, object]:
    if not isinstance(facts, dict):
        return {}
    service_date = facts.get("service_date")
    return {"service_date": service_date} if isinstance(service_date, str) else {}


def _timeline_row(row: dict[str, object]) -> dict[str, object]:
    recipient = row.get("recipient_identity")
    return {
        "source_event_id": int(row["source_event_id"]),
        "event_code": str(row["event_code"]),
        "occurred_at_utc": str(row["occurred_at_utc"]),
        "historical_silent": bool(row["historical_silent"]),
        "rule_id": row.get("rule_id"),
        "decision_status": row.get("decision_status"),
        "reason_code": row.get("reason_code"),
        "recipient_type": row.get("recipient_type"),
        "recipient_masked": _mask_recipient(recipient),
        "occurrence_number": row.get("occurrence_number"),
        "intent_status": row.get("intent_status"),
        "scheduled_at_utc": None if row.get("scheduled_at_utc") is None else str(row["scheduled_at_utc"]),
        "delivery_status": row.get("processing_status"),
        "delivery_task_id": row.get("delivery_task_id"),
    }


def _mask_recipient(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return "***" + value[-4:]

_CANCEL_DELIVERY_TASKS_SQL = (
    "UPDATE line_delivery_tasks AS task "
    "JOIN line_notification_intents AS intent ON intent.delivery_task_id=task.id "
    "JOIN line_notification_decisions AS decision ON decision.id=intent.decision_id "
    "SET task.processing_status='cancelled',task.error_code=%s,"
    "task.error_message='notification rule deleted',task.lease_owner=NULL,"
    "task.lease_acquired_at_utc=NULL,task.lease_expires_at_utc=NULL "
    "WHERE decision.rule_id=%s AND intent.intent_status='cancelled' "
    "AND task.processing_status IN ('pending','retryable_failed','processing')"
)


__all__ = ["MySqlLineNotificationRepository"]

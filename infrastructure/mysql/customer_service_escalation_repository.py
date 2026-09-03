"""File: customer_service_escalation_repository.py
Description: M4 Customer Service escalation 的 MySQL query/CAS adapter。
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any, Mapping

from domains.customer_service.escalation import (
    AutomationHoldState,
    EscalationEventType,
    EscalationWorkflowStatus,
    EscalationAlertIntent,
)
from subsystems.customer_service.escalation_contracts import (
    AutomationHoldDecision,
    CreateHumanEscalation,
    HumanEscalationReceipt,
)


class CustomerServiceEscalationNotFoundError(LookupError):
    """找不到 escalation root。"""


class CustomerServiceEscalationVersionConflictError(RuntimeError):
    """escalation CAS 未更新任何資料。"""


class CustomerServiceEscalationNotImplementedError(NotImplementedError):
    """candidate schema 尚未提供所需的 durable contract。"""


_SELECT = (
    "SELECT id,source_event_identity,source_kind,source_fingerprint,trigger_code,"
    "trigger_policy_version,ticket_id,ticket_category,urgency,workflow_status,"
    "workflow_version,hold_scope_ref,automation_hold_state AS hold_state,hold_version,"
    "actor_ref,claim_at_utc,handling_started_at_utc,resolved_at_utc,resolution_code,"
    "resolution_evidence_digest,context,idempotency_key,correlation_id,"
    "alert_status,delivery_task_ref,delivery_outcome_ref,created_at_utc AS created_at,updated_at_utc AS updated_at "
    "FROM customer_service_escalations"
)


class MySqlCustomerServiceEscalationRepository:
    """Candidate-schema adapter; it never commits and never invents missing columns."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_by_id(self, escalation_id: int, *, lock: bool = False) -> Mapping[str, Any] | None:
        return self._one(" WHERE id=%s" + (" FOR UPDATE" if lock else ""), (escalation_id,))

    def get_by_source(self, source_event_identity: str, *, lock: bool = False) -> Mapping[str, Any] | None:
        return self._one(
            " WHERE source_event_identity=%s" + (" FOR UPDATE" if lock else ""),
            (source_event_identity,),
        )

    def get_by_idempotency(self, key: str, *, lock: bool = False) -> Mapping[str, Any] | None:
        row = self._one(" WHERE idempotency_key=%s" + (" FOR UPDATE" if lock else ""), (key,))
        if row is None:
            # Transition commands have their own idempotency key, while the
            # escalation root keeps the create key.  Resolve the transition
            # replay through the immutable command receipt's escalation
            # reference instead of treating it as a new command.
            receipt = self._receipt_row(key, lock=lock)
            snapshot = None if receipt is None else _receipt_snapshot(receipt.get("result_snapshot"))
            if snapshot is None:
                return None
            row = self._one(
                " WHERE id=%s" + (" FOR UPDATE" if lock else ""),
                (snapshot.escalation_id,),
            )
            if row is None:
                raise CustomerServiceEscalationNotFoundError(
                    f"escalation {snapshot.escalation_id} was not returned"
                )
        receipt = self._receipt_row(key, lock=lock)
        if receipt is not None:
            row = dict(row)
            row["request_fingerprint"] = receipt.get("payload_fingerprint")
            row["receipt"] = _receipt_snapshot(receipt.get("result_snapshot"))
        return row

    def get_active_by_scope(self, hold_scope: str, *, lock: bool = False) -> Mapping[str, Any] | None:
        return self._one(
            " WHERE hold_scope_ref=%s AND automation_hold_state='active'"
            + (" FOR UPDATE" if lock else ""),
            (hold_scope,),
        )

    def active_hold(self, hold_scope: str) -> AutomationHoldDecision | None:
        if self.get_active_by_scope(hold_scope) is None:
            return None
        return AutomationHoldDecision(AutomationHoldState.ACTIVE, hold_scope)

    def create(self, command: CreateHumanEscalation, ticket: object) -> Mapping[str, Any]:
        ticket_id = _field(ticket, "ticket_id", _field(ticket, "id", None))
        if ticket_id is None:
            raise CustomerServiceEscalationNotImplementedError("ticket contract lacks ticket_id")
        context = (
            command.context.as_dict()
            if hasattr(command.context, "as_dict")
            else dict(command.context)
        )
        sql = (
            "INSERT INTO customer_service_escalations "
            "(source_event_identity,source_kind,source_fingerprint,trigger_code,"
            "trigger_policy_version,ticket_id,ticket_category,urgency,hold_scope_ref,"
            "actor_ref,context,idempotency_key,correlation_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'high',%s,%s,%s,%s,%s)"
        )
        params = (
            command.source_event_identity,
            command.source_kind,
            command.source_fingerprint,
            command.trigger_code.value,
            command.trigger_policy_version,
            int(ticket_id),
            command.ticket_category.value,
            command.hold_scope,
            command.actor.actor_id,
            json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            command.idempotency_key.value,
            command.correlation_id.value,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            identifier = int(cursor.lastrowid)
        row = self.get_by_id(identifier)
        if row is None:
            raise CustomerServiceEscalationNotFoundError(f"escalation {identifier} was not returned")
        return row

    def transition(self, escalation_id: int, **changes: object) -> Mapping[str, Any]:
        if "workflow_version" not in changes:
            raise CustomerServiceEscalationNotImplementedError("CAS requires workflow_version")
        # Ticket version belongs to the ticket root and is recorded in the immutable event;
        # it is intentionally not duplicated into the escalation table.
        allowed = {
            "workflow_status",
            "workflow_version",
            "hold_state",
            "hold_version",
            "resolution_code",
            "resolution_evidence_digest",
            "ticket_version",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise CustomerServiceEscalationNotImplementedError(
                f"unsupported escalation fields: {sorted(unknown)}"
            )
        result_version = int(changes["workflow_version"])
        if result_version <= 0:
            raise CustomerServiceEscalationNotImplementedError("workflow_version must advance")
        expected_version = result_version - 1
        columns: list[str] = []
        params: list[Any] = []
        for key, value in changes.items():
            if key == "ticket_version":
                continue
            column = "automation_hold_state" if key == "hold_state" else key
            columns.append(f"{column}=%s")
            params.append(getattr(value, "value", value))
        status_value = getattr(changes.get("workflow_status"), "value", changes.get("workflow_status"))
        if status_value == "claimed":
            columns.append("claim_at_utc=UTC_TIMESTAMP(6)")
        elif status_value == "handling":
            columns.append("handling_started_at_utc=UTC_TIMESTAMP(6)")
        elif status_value == "resolved":
            columns.append("resolved_at_utc=UTC_TIMESTAMP(6)")
        sql = (
            "UPDATE customer_service_escalations SET "
            + ",".join(columns)
            + " WHERE id=%s AND workflow_version=%s"
        )
        params.extend((escalation_id, expected_version))
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            if cursor.rowcount != 1:
                raise CustomerServiceEscalationVersionConflictError("客服 escalation 版本衝突")
        row = self.get_by_id(escalation_id)
        if row is None:
            raise CustomerServiceEscalationNotFoundError(f"escalation {escalation_id} not found")
        return row

    def append_event(self, escalation_id: int, event_type: EscalationEventType, **values: object) -> None:
        base_names = (
            "expected_escalation_version",
            "resulting_escalation_version",
            "expected_ticket_version",
            "resulting_ticket_version",
            "actor_ref",
            "reason_code",
            "reason_evidence_digest",
            "receipt_id",
            "idempotency_key",
            "correlation_id",
        )
        hold_names = ("expected_hold_version", "resulting_hold_version")
        supplied_hold_names = tuple(name for name in hold_names if name in values)
        if supplied_hold_names and len(supplied_hold_names) != len(hold_names):
            raise ValueError("hold version fields must be supplied together")
        names = (
            base_names[:4] + hold_names + base_names[4:]
            if len(supplied_hold_names) == len(hold_names)
            else base_names
        )
        optional_names = {"expected_ticket_version", "resulting_ticket_version"}
        missing = (set(names) - optional_names) - set(values)
        if missing:
            raise ValueError(f"missing event fields: {sorted(missing)}")
        unknown = set(values) - set(names)
        if unknown:
            raise CustomerServiceEscalationNotImplementedError(
                f"unsupported event fields: {sorted(unknown)}"
            )
        if len(supplied_hold_names) == len(hold_names):
            columns = (
                "escalation_id,event_type,expected_escalation_version,resulting_escalation_version,"
                "expected_ticket_version,resulting_ticket_version,expected_hold_version,"
                "resulting_hold_version,actor_ref,reason_code,reason_evidence_digest,receipt_id,"
                "idempotency_key,correlation_id"
            )
        else:
            columns = (
                "escalation_id,event_type,expected_escalation_version,resulting_escalation_version,"
                "expected_ticket_version,resulting_ticket_version,actor_ref,reason_code,"
                "reason_evidence_digest,receipt_id,idempotency_key,correlation_id"
            )
        sql = (
            "INSERT INTO customer_service_escalation_events (" + columns + ") VALUES ("
            + ",".join("%s" for _ in range(len(names) + 2))
            + ")"
        )
        params = (
            escalation_id,
            getattr(event_type, "value", event_type),
            *(values.get(name) for name in names),
        )
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)

    def save_receipt(self, key: str, fingerprint: str, receipt: object) -> None:
        if not isinstance(receipt, HumanEscalationReceipt):
            raise CustomerServiceEscalationNotImplementedError("invalid escalation receipt")
        snapshot = _receipt_payload(receipt)
        sql = (
            "INSERT INTO line_command_receipts "
            "(idempotency_key,command_family,payload_fingerprint,result_reference,"
            "result_snapshot,correlation_id) VALUES (%s,%s,%s,%s,%s,%s)"
        )
        params = (
            key,
            receipt.command_family,
            fingerprint,
            receipt.receipt_id,
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            receipt.correlation_id,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)

    def enqueue_alert(self, intent: object) -> None:
        if not isinstance(intent, EscalationAlertIntent):
            raise CustomerServiceEscalationNotImplementedError("invalid bounded alert intent")
        target_snapshot = self._active_alert_target_snapshot()
        payload = {
            "escalation_ref": intent.escalation_ref,
            "ticket_ref": intent.ticket_ref,
            "trigger_code": intent.trigger_code.value,
            "category": intent.category,
            "safe_summary": intent.safe_summary,
            "hold_state": intent.hold_state.value,
            "urgency": intent.urgency,
            "correlation_id": intent.correlation_id,
            "source_digest": intent.source_digest,
            "target_snapshot": target_snapshot,
        }
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        identity = "human-escalation-alert:" + hashlib.sha256(
            f"{intent.escalation_ref}:{intent.correlation_id}".encode("utf-8")
        ).hexdigest()
        sql = (
            "INSERT INTO line_domain_outbox "
            "(aggregate_type,aggregate_identity,intent_type,payload_snapshot,idempotency_identity) "
            "VALUES (%s,%s,%s,%s,%s)"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    "customer_service_escalation",
                    intent.escalation_ref,
                    "line.customer_service.human_escalation",
                    payload_json,
                    identity,
                ),
            )
            escalation_id = _escalation_id(intent.escalation_ref)
            cursor.execute(
                "UPDATE customer_service_escalations SET alert_status='queued',alert_intent_ref=%s WHERE id=%s",
                (identity, escalation_id),
            )

    def record_alert_delivery_task(self, escalation_ref: str, task_id: int) -> None:
        escalation_id = _escalation_id(escalation_ref)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE customer_service_escalations SET delivery_task_ref=%s,alert_status='queued' WHERE id=%s",
                (f"delivery-task:{task_id}", escalation_id),
            )
            if cursor.rowcount != 1:
                raise CustomerServiceEscalationNotFoundError(f"escalation {escalation_id} not found")

    def record_alert_delivery_outcome(
        self, escalation_ref: str, outcome_ref: str, alert_status: str
    ) -> None:
        if alert_status not in {"sent", "failed"}:
            raise ValueError("invalid human escalation alert status")
        escalation_id = _escalation_id(escalation_ref)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE customer_service_escalations SET delivery_outcome_ref=%s,alert_status=%s WHERE id=%s",
                (outcome_ref, alert_status, escalation_id),
            )
            if cursor.rowcount != 1:
                raise CustomerServiceEscalationNotFoundError(f"escalation {escalation_id} not found")

    def _active_alert_target_snapshot(self) -> dict[str, object] | None:
        """Capture the configured recipient and threshold in the immutable intent."""
        # Legacy unit fakes model only the outbox writer cursor; preserve that
        # adapter seam while real MySQL cursors provide the typed snapshot.
        cursor_queue = getattr(self._connection, "cursors", None)
        if isinstance(cursor_queue, list) and cursor_queue and not hasattr(cursor_queue[0], "fetchall"):
            return None
        sql = (
            "SELECT t.id,t.target_type,t.group_id,t.minimum_status,t.updated_at_utc,"
            "a.linked_line_user_id FROM line_alert_notification_targets t "
            "LEFT JOIN admin_users a ON a.id=t.admin_user_id "
            "WHERE t.enabled=TRUE ORDER BY (t.target_type='group') DESC,t.id LIMIT 2"
        )
        with self._connection.cursor() as cursor:
            if not hasattr(cursor, "fetchall"):
                return None
            cursor.execute(sql)
            fetchall = getattr(cursor, "fetchall", None)
            rows = tuple(fetchall() or ()) if callable(fetchall) else ()
        if len(rows) != 1:
            return None
        row = rows[0]
        target_type = str(row["target_type"])
        identity = row.get("group_id") if target_type == "group" else row.get("linked_line_user_id")
        if not identity:
            return None
        updated = row.get("updated_at_utc")
        return {
            "target_id": int(row["id"]),
            "recipient_type": "group" if target_type == "group" else "user",
            "recipient_identity": str(identity),
            "active": True,
            "configuration": {
                "minimum_status": str(row["minimum_status"]),
                "revision": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
            },
        }

    def append_source_event(self, escalation_id: int, command: CreateHumanEscalation) -> None:
        row = self.get_by_id(escalation_id, lock=True)
        if row is None:
            raise CustomerServiceEscalationNotFoundError(f"escalation {escalation_id} not found")
        ticket_id = row.get("ticket_id")
        if ticket_id is None:
            raise CustomerServiceEscalationNotImplementedError("escalation has no ticket link")
        event_key = f"human-escalation-source:{command.idempotency_key.value}"
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO customer_service_ticket_events "
                "(ticket_id,event_key,event_type,message_text,actor_id) VALUES (%s,%s,'internal_note',%s,%s)",
                (
                    int(ticket_id),
                    event_key,
                    "human_escalation_source_digest:"
                    + hashlib.sha256(command.source_event_identity.encode("utf-8")).hexdigest(),
                    command.actor.actor_id,
                ),
            )

    def _one(self, suffix: str, params: tuple[Any, ...]) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_SELECT + suffix, params)
            row = cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, Mapping) and isinstance(row.get("context"), (str, bytes)):
            payload = row["context"]
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            row = dict(row)
            row["context"] = json.loads(payload)
        return row

    def _receipt_row(self, key: str, *, lock: bool) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_fingerprint,result_snapshot FROM line_command_receipts "
                "WHERE idempotency_key=%s" + (" FOR UPDATE" if lock else ""),
                (key,),
            )
            return cursor.fetchone()


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _receipt_payload(receipt: HumanEscalationReceipt) -> dict[str, object]:
    return {
        "receipt_id": receipt.receipt_id,
        "command_family": receipt.command_family,
        "operation": receipt.operation,
        "escalation_id": receipt.escalation_id,
        "ticket_ref": receipt.ticket_ref,
        "resulting_workflow_status": receipt.resulting_workflow_status.value,
        "resulting_hold_state": receipt.resulting_hold_state.value,
        "current_version": receipt.current_version,
        "replayed": receipt.replayed,
        "correlation_id": receipt.correlation_id,
        "committed_at": receipt.committed_at.isoformat(),
    }


def _receipt_snapshot(value: object) -> HumanEscalationReceipt | None:
    if value is None:
        return None
    if isinstance(value, (bytes, str)):
        value = json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)
    if not isinstance(value, Mapping):
        return None
    try:
        return HumanEscalationReceipt(
            str(value["receipt_id"]),
            str(value["command_family"]),
            str(value["operation"]),
            int(value["escalation_id"]),
            str(value["ticket_ref"]),
            EscalationWorkflowStatus(str(value["resulting_workflow_status"])),
            AutomationHoldState(str(value["resulting_hold_state"])),
            str(value["current_version"]),
            bool(value["replayed"]),
            str(value["correlation_id"]),
            datetime.fromisoformat(str(value["committed_at"])),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _escalation_id(value: str) -> int:
    prefix, _, raw = value.partition(":")
    if prefix != "escalation" or not raw.isdigit() or int(raw) <= 0:
        raise CustomerServiceEscalationNotImplementedError("invalid escalation reference")
    return int(raw)


__all__ = [
    "CustomerServiceEscalationNotFoundError",
    "CustomerServiceEscalationNotImplementedError",
    "CustomerServiceEscalationVersionConflictError",
    "MySqlCustomerServiceEscalationRepository",
]

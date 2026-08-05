"""MySQL persistence adapter for the canonical Orders auto-completion command."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pymysql.err import IntegrityError

from domains.orders.auto_completion import AutoCompletionCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.auto_completion_workflow import (
    AutoCompletionApplyRequest,
    AutoCompletionClaimState,
    AutoCompletionReceipt,
    StoredAutoCompletionReceipt,
)
from subsystems.orders.lifecycle_authoritative_facts_loader import (
    load_order_lifecycle_authoritative_facts,
)
from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)

_COMMAND_FAMILY = "orders_auto_completion"


class MySqlOrderAutoCompletionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def claim_command(self, request, fingerprint):
        with self._connection.cursor() as cursor:
            if _insert_claim(cursor, request, fingerprint):
                return AutoCompletionClaimState.CREATED
            row = _lock_claim(cursor, request.idempotency_key)
        expected = (_COMMAND_FAMILY, request.case_no, fingerprint.value)
        actual = (str(row["command_family"]), str(row["aggregate_identity"]), str(row["command_fingerprint"]))
        return AutoCompletionClaimState.MATCHED if actual == expected else AutoCompletionClaimState.MISMATCH

    def find_receipt(self, key: IdempotencyKey):
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def load_locked_facts(self, request):
        with self._connection.cursor() as cursor:
            envelope = lock_order_lifecycle_command_envelope(cursor, request.case_no, request.expected_order_version.value, request.idempotency_key.value)
            return load_order_lifecycle_authoritative_facts(cursor, envelope, "evaluation_time_reached", request.evaluation_at)

    def append_lifecycle_event(self, request, candidate, facts):
        snapshot = _lifecycle_snapshot(request, candidate, facts)
        with self._connection.cursor() as cursor:
            cursor.execute(_LIFECYCLE_EVENT_INSERT_SQL, (request.case_no, "evaluation_time_reached", "服務中", "訂單完成", request.actor.actor_id, candidate.evaluation_at.date(), candidate.expected_order_version, request.idempotency_key.value, _json(snapshot)))
            return int(cursor.lastrowid)

    def update_order(self, candidate: AutoCompletionCandidate) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_UPDATE_SQL, ("訂單完成", candidate.resulting_order_version, candidate.case_no, candidate.expected_order_version))
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")

    def append_outbox(self, request, candidate, lifecycle_event_id):
        payload = {"after_status": "訂單完成", "completion_instant": candidate.completion_instant.isoformat(), "correlation_id": request.correlation_id.value, "resulting_order_version": candidate.resulting_order_version}
        with self._connection.cursor() as cursor:
            cursor.execute(_OUTBOX_INSERT_SQL, (request.case_no, lifecycle_event_id, _child_identity(request, "orders-outbox"), "lifecycle_projection_changed", _json(payload)))

    def save_receipt(self, receipt: AutoCompletionReceipt) -> None:
        payload = _receipt_payload(receipt)
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, (receipt.idempotency_key.value, receipt.command_fingerprint.value, receipt.case_no, receipt.lifecycle_event_id, receipt.order_version, receipt.completion_instant, receipt.evaluation_at, _json(payload)))


def _insert_claim(cursor, request, fingerprint):
    try:
        cursor.execute(_CLAIM_INSERT_SQL, (request.idempotency_key.value, _COMMAND_FAMILY, request.case_no, fingerprint.value, request.correlation_id.value))
    except IntegrityError as error:
        if _mysql_error_code(error) != 1062:
            raise
        return False
    return True


def _lock_claim(cursor, key):
    cursor.execute(_CLAIM_SELECT_SQL, (key.value,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return row


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = AutoCompletionReceipt(str(payload["case_no"]), IdempotencyKey(str(row["idempotency_key"])), int(payload["order_version"]), int(payload["lifecycle_event_id"]), _as_datetime(payload["completion_instant"]), _as_datetime(payload["evaluation_at"]), PreviewFingerprint(str(row["command_fingerprint"])))
    if str(row["case_no"]) != receipt.case_no or int(row["order_version"]) != receipt.order_version or int(row["lifecycle_event_id"]) != receipt.lifecycle_event_id:
        raise ValueError("order_auto_completion_receipt_integrity_violation")
    return StoredAutoCompletionReceipt(PreviewFingerprint(str(row["command_fingerprint"])), receipt)


def _lifecycle_snapshot(request, candidate, facts):
    return {"authoritative_facts": facts["authoritative_facts"], "completion_instant": candidate.completion_instant.isoformat(), "correlation_id": request.correlation_id.value, "reason": request.reason, "resulting_order_version": candidate.resulting_order_version}


def _receipt_payload(receipt):
    return {"case_no": receipt.case_no, "completion_instant": receipt.completion_instant.isoformat(), "evaluation_at": receipt.evaluation_at.isoformat(), "lifecycle_event_id": receipt.lifecycle_event_id, "order_version": receipt.order_version}


def _child_identity(request, purpose):
    return "child:" + fingerprint_payload({"domain": "orders", "outer_key": request.idempotency_key.value, "purpose": purpose}).value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("order_auto_completion_receipt_integrity_violation")
    return parsed


def _as_datetime(value):
    if not isinstance(value, str):
        raise ValueError("order_auto_completion_receipt_integrity_violation")
    from datetime import datetime
    return datetime.fromisoformat(value)


def _mysql_error_code(error):
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


_CLAIM_INSERT_SQL = "INSERT INTO application_command_claims (idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
_CLAIM_SELECT_SQL = "SELECT command_family,aggregate_identity,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE"
_LIFECYCLE_EVENT_INSERT_SQL = "INSERT INTO order_lifecycle_state_events (case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
_ORDER_UPDATE_SQL = "UPDATE orders SET status=%s,lifecycle_version=%s WHERE case_no=%s AND lifecycle_version=%s"
_OUTBOX_INSERT_SQL = "INSERT INTO orders_domain_outbox (case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,%s,%s,%s)"
_RECEIPT_SELECT_SQL = "SELECT idempotency_key,command_fingerprint,case_no,lifecycle_event_id,order_version,result_snapshot FROM order_auto_completion_apply_receipts WHERE idempotency_key=%s FOR UPDATE"
_RECEIPT_INSERT_SQL = "INSERT INTO order_auto_completion_apply_receipts (idempotency_key,command_fingerprint,case_no,lifecycle_event_id,order_version,completion_instant,evaluation_at,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"


__all__ = ["MySqlOrderAutoCompletionRepository"]

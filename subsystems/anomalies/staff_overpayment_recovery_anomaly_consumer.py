"""
File: staff_overpayment_recovery_anomaly_consumer.py
Description: 以 fresh Staff recovery root 投影 established、追償進度與終止事件。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import re

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication, RootFactProjectionError

_EVENT_TYPES = frozenset({
    "staff_overpayment_recovery_established",
    "staff_overpayment_recovery_matched",
    "staff_overpayment_recovery_updated",
    "staff_overpayment_recovery_collected",
})
_ACTIVE_STATUSES = frozenset({"open", "partially_recovered"})
_BANK_FACT_IDENTITY = re.compile(r"^finance-import-row:([1-9][0-9]*)$")
_MAXIMUM_PROJECTION_ATTEMPTS = 3


def consume_staff_overpayment_recovery_anomaly_events(connection, maximum_events: int = 50) -> tuple[int, int]:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim(connection)
        if event is None:
            connection.rollback()
            break
        try:
            payload = _payload(event["payload_snapshot"])
            event_type = _event_type(event, payload)
            source = _source(connection, payload)
            root_fact = build_staff_overpayment_recovery_root_fact(event, source, event_type=event_type)
            _project(connection, event, root_fact)
            _delivered(connection, int(event["id"]))
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            _failed(connection, int(event["id"]))
            failed += 1
    return delivered, failed


def _project(connection, event, root_fact) -> None:
    try:
        RootFactProjectionApplication(
            default_anomaly_registry(), MySqlRootFactProjectionRepository(connection), BorrowedProjectionUnitOfWork,
        ).project(root_fact, CorrelationId(f"staff-overpayment-recovery:{event['id']}"))
    except RootFactProjectionError as error:
        if error.error.code != "anomaly_projection_stale":
            raise


def build_staff_overpayment_recovery_root_fact(event, source, *, event_type: str | None = None) -> FinanceManualReviewRootFact:
    identity = _text(source["recovery_identity"], "recovery identity")
    status = _text(source["status"], "recovery status")
    if status not in {"open", "partially_recovered", "recovered", "adjusted"}:
        raise ValueError("staff recovery status is invalid")
    remaining = _nonnegative(source["remaining_amount_ntd"], "remaining amount")
    if (status in _ACTIVE_STATUSES) != (remaining > 0):
        raise ValueError("staff recovery status and remaining are inconsistent")
    resolved_event_type = event_type or (
        "staff_overpayment_recovery_matched"
        if source.get("matching_identity")
        else "staff_overpayment_recovery_updated"
    )
    root_active = status in _ACTIVE_STATUSES and remaining > 0
    bindings: list[tuple[str, str | int]] = [
        ("recovery_identity", identity),
        ("recovery_version", _nonnegative(source["recovery_version"], "recovery version")),
        ("staff_id", _positive(source["staff_id"])),
        ("staff_payables_version", _nonnegative(source["staff_payables_version"], "staff payables version")),
    ]
    if source.get("matching_identity") is not None:
        bindings.extend((
            ("finance_import_row_identity", str(_positive(source["finance_import_row_id"]))),
            ("matching_identity", _text(source["matching_identity"], "matching identity")),
            ("matching_version", _positive(source["matching_version"])),
        ))
    return FinanceManualReviewRootFact(
        source_event_identity=f"staff-overpayment-recovery:{identity}:{_positive(event['id'])}",
        source_version=_positive(event["id"]), origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]), finance_import_row_id=_positive(source["finance_import_row_id"]),
        finance_import_batch_id=_positive(source["finance_import_batch_id"]), active=root_active,
        integrity_blocker_active=False, amount_delta_ntd=remaining,
        reason_codes=(resolved_event_type,), definition_code="staff_overpayment_recovery_open",
        source_identity_override=f"staff-overpayment-recovery:{identity}", recovery_bindings=tuple(sorted(bindings)),
    )


def _claim(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,intent_type,payload_snapshot,created_at FROM staff_payables_outbox "
            "WHERE intent_type IN ('staff_overpayment_recovery_updated',"
            "'staff_overpayment_recovery_matched','staff_overpayment_recovery_collected') "
            f"AND status IN ('pending','failed') AND attempt_count<{_MAXIMUM_PROJECTION_ATTEMPTS} "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _source(connection, payload):
    identity = _text(payload.get("recovery_identity"), "recovery identity")
    matching_identity = payload.get("matching_identity")
    if matching_identity is not None:
        matching_identity = _text(matching_identity, "matching identity")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT recovery_identity,staff_id,remaining_amount_ntd,status,aggregate_version,source_bank_fact_identities "
            "FROM staff_overpayment_recoveries WHERE recovery_identity=%s FOR UPDATE", (identity,)
        )
        recovery = cursor.fetchone()
        if recovery is None:
            raise ValueError("staff_overpayment_recovery_root_not_found")
        cursor.execute("SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s FOR UPDATE", (int(recovery["staff_id"]),))
        account = cursor.fetchone()
        if account is None:
            raise ValueError("staff_overpayment_recovery_staff_account_not_found")
        bank_id = _bank_ids(recovery["source_bank_fact_identities"])[0]
        cursor.execute("SELECT id,batch_id FROM finance_import_rows WHERE id=%s FOR UPDATE", (bank_id,))
        bank = cursor.fetchone()
        if bank is None or bank["batch_id"] is None:
            raise ValueError("staff_overpayment_recovery_source_bank_fact_not_found")
        source = {
            "recovery_identity": str(recovery["recovery_identity"]), "staff_id": int(recovery["staff_id"]),
            "remaining_amount_ntd": int(recovery["remaining_amount_ntd"]), "status": str(recovery["status"]),
            "recovery_version": int(recovery["aggregate_version"]), "staff_payables_version": int(account["aggregate_version"]),
            "finance_import_row_id": int(bank["id"]), "finance_import_batch_id": int(bank["batch_id"]),
        }
        if matching_identity is not None:
            cursor.execute(
                "SELECT matching_identity,finance_import_row_id,matching_version FROM staff_overpayment_recovery_matchings "
                "WHERE matching_identity=%s AND recovery_identity=%s AND staff_id=%s FOR UPDATE",
                (matching_identity, identity, source["staff_id"]),
            )
            matching = cursor.fetchone()
            if matching is None:
                raise ValueError("staff_overpayment_recovery_matching_not_found")
            source.update(matching_identity=str(matching["matching_identity"]), matching_version=int(matching["matching_version"]), finance_import_row_id=int(matching["finance_import_row_id"]))
            cursor.execute("SELECT batch_id FROM finance_import_rows WHERE id=%s FOR UPDATE", (source["finance_import_row_id"],))
            matching_bank = cursor.fetchone()
            if matching_bank is None or matching_bank["batch_id"] is None:
                raise ValueError("staff_overpayment_recovery_matching_bank_fact_not_found")
            source["finance_import_batch_id"] = int(matching_bank["batch_id"])
    return source


def _event_type(event, payload):
    intent_type = _text(event["intent_type"], "outbox intent type")
    event_type = payload.get("event_type")
    if event_type is None:
        event_type = intent_type
    event_type = _text(event_type, "staff recovery event type")
    if event_type not in _EVENT_TYPES:
        raise ValueError("staff recovery event intent mismatch")
    if event_type == "staff_overpayment_recovery_established":
        if intent_type not in {"staff_overpayment_recovery_established", "staff_overpayment_recovery_updated"}:
            raise ValueError("staff recovery event intent mismatch")
    elif event_type != intent_type:
        raise ValueError("staff recovery event intent mismatch")
    return event_type


def _delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE staff_payables_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (event_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("staff_overpayment_recovery_outbox_delivery_conflict")


def _failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE staff_payables_outbox SET status='failed',attempt_count=attempt_count+1,"
            f"next_attempt_at=CASE WHEN attempt_count+1>={_MAXIMUM_PROJECTION_ATTEMPTS} "
            "THEN NULL ELSE DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND) END,"
            "last_error='staff_recovery_anomaly_projection_failed' "
            "WHERE id=%s AND status IN ('pending','failed')",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("staff_overpayment_recovery_outbox_failure_conflict")
    connection.commit()


def _payload(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("staff recovery payload is invalid")
    return parsed


def _bank_ids(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("staff recovery source bank facts are invalid")
    result = []
    for item in parsed:
        if not isinstance(item, str):
            raise ValueError("staff recovery source bank fact identity is invalid")
        match = _BANK_FACT_IDENTITY.fullmatch(item)
        if match is None:
            raise ValueError("staff recovery source bank fact identity is invalid")
        result.append(int(match.group(1)))
    return tuple(result)


def _text(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    return value


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("staff recovery positive value is invalid")
    return value


def _nonnegative(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} is invalid")
    return value


def _aware(value):
    if not isinstance(value, datetime):
        raise ValueError("staff recovery event timestamp is invalid")
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


__all__ = ["build_staff_overpayment_recovery_root_fact", "consume_staff_overpayment_recovery_anomaly_events"]

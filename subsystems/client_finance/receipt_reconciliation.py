"""Reconcile one classified bank receipt inside the caller's transaction.

The Finance Import diagnostic invokes this command without owning its outer
transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Callable

from domains.finance_import.cancellation_code import resolve_finance_cancellation_code
from shared_kernel.business_time import current_business_instant
from subsystems.client_finance.virtual_account_resolution import (
    resolve_client_virtual_account,
)

_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_LIFECYCLE_ACTOR = "finance-import:client-receipt"
_SAVEPOINT = "client_receipt_snapshot"
_STAGES = ("deposit", "first_payment", "second_payment")

_create_client_payment_snapshot: Callable[..., Mapping[str, Any]] | None = None
_record_client_payment_transaction: Callable[..., Mapping[str, Any]] | None = None
_lock_order_lifecycle_command_envelope: Callable[..., Any] | None = None


def configure_receipt_reconciliation_dependencies(
    *,
    create_snapshot: Callable[..., Mapping[str, Any]],
    record_transaction: Callable[..., Mapping[str, Any]],
    lock_lifecycle_command: Callable[..., Any],
) -> None:
    """Bind the command collaborators supplied by the transaction boundary."""
    global _create_client_payment_snapshot
    global _record_client_payment_transaction
    global _lock_order_lifecycle_command_envelope
    _create_client_payment_snapshot = create_snapshot
    _record_client_payment_transaction = record_transaction
    _lock_order_lifecycle_command_envelope = lock_lifecycle_command


def _dependencies() -> tuple[Callable[..., Mapping[str, Any]], Callable[..., Mapping[str, Any]], Callable[..., Mapping[str, Any]], Callable[..., Any]]:
    dependencies = (
        _create_client_payment_snapshot,
        _record_client_payment_transaction,
        _lock_order_lifecycle_command_envelope,
    )
    if any(dependency is None for dependency in dependencies):
        raise RuntimeError("client receipt legacy dependencies are not recovered")
    create_snapshot, record_transaction, lock_lifecycle_command = dependencies
    return (
        create_snapshot,
        record_transaction,
        resolve_client_virtual_account,
        lock_lifecycle_command,
    )  # type: ignore[return-value]


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return value


def _bank_references(value: Any) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("bank_references must contain valid JSON") from exc
    return _mapping(value, "bank_references")


def _transaction_date(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def _pending(reason: str, case_no: str | None = None) -> dict[str, Any]:
    return {"result": "pending", "reason": reason, "transaction_ids": [], "client_payment_id": None, "case_no": case_no}


def _rollback_snapshot(cursor: Any) -> None:
    cursor.execute(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT}")
    cursor.execute(f"RELEASE SAVEPOINT {_SAVEPOINT}")


def _load_payment(cursor: Any, client_payment_id: int) -> Mapping[str, Any]:
    cursor.execute(
        "SELECT id, case_no, deposit_receivable, deposit_received,\n"
        "       first_payment_receivable, first_payment_received,\n"
        "       second_payment_receivable, second_payment_received\n"
        "FROM client_payments WHERE id = %s FOR UPDATE",
        (client_payment_id,),
    )
    payment = cursor.fetchone()
    if payment is None:
        raise ValueError("client payment snapshot does not exist")
    return _mapping(payment, "client payment")


def _lifecycle_expected_version(cursor: Any, case_no: str, idempotency_key: str) -> int:
    cursor.execute(
        "SELECT o.lifecycle_version,\n"
        "       lifecycle_event.expected_version AS existing_expected_version\n"
        "FROM orders AS o\n"
        "LEFT JOIN order_lifecycle_state_events AS lifecycle_event\n"
        "  ON lifecycle_event.case_no = o.case_no\n"
        " AND lifecycle_event.idempotency_key = %s\n"
        "WHERE o.case_no = %s",
        (idempotency_key, case_no),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("resolved order does not exist")
    value = _mapping(row, "lifecycle version").get("existing_expected_version")
    if value is None:
        value = row.get("lifecycle_version")
    if isinstance(value, bool):
        raise ValueError("order lifecycle version must be a non-negative integer")
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("order lifecycle version must be a non-negative integer") from exc
    if version < 0 or version != value:
        raise ValueError("order lifecycle version must be a non-negative integer")
    return version


def _replay_evaluation_at(command_envelope: Any, observed_at: datetime) -> datetime:
    existing = getattr(command_envelope, "existing_lifecycle_event", None)
    if existing is None:
        return observed_at
    facts = _mapping(existing, "existing lifecycle event").get("facts_snapshot")
    if isinstance(facts, str):
        try:
            facts = json.loads(facts)
        except json.JSONDecodeError as exc:
            raise ValueError("existing lifecycle facts_snapshot must contain valid JSON") from exc
    value = _mapping(facts, "existing lifecycle facts_snapshot").get("evaluation_at")
    if not isinstance(value, str):
        raise ValueError("existing lifecycle facts_snapshot must contain evaluation_at")
    try:
        replay_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("existing lifecycle evaluation_at must be an ISO datetime") from exc
    if replay_at.tzinfo is None:
        raise ValueError("existing lifecycle evaluation_at must be timezone-aware")
    return replay_at


def _allocate(receivables: Mapping[str, Any], received: Mapping[str, Any], credit: Decimal) -> list[tuple[str, Decimal]] | None:
    remaining = credit
    allocations: list[tuple[str, Decimal]] = []
    for stage in _STAGES:
        stage_remaining = _decimal(receivables[stage], f"{stage}_receivable") - _decimal(received[stage], f"{stage}_received")
        if stage_remaining < 0:
            raise ValueError("client payment summary exceeds its receivable snapshot")
        amount = min(remaining, stage_remaining)
        if amount > 0:
            allocations.append((stage, amount))
            remaining -= amount
        if remaining == 0:
            return allocations
    return None


def _payment_amounts(payment: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return ({stage: payment[f"{stage}_receivable"] for stage in _STAGES}, {stage: payment[f"{stage}_received"] for stage in _STAGES})


def _validate_existing_set(rows: list[Mapping[str, Any]], *, payment: Mapping[str, Any], finance_import_row_id: int, fingerprint: str, credit: Decimal, occurred_at: str) -> list[int]:
    by_stage: dict[str, Mapping[str, Any]] = {}
    prior_received = {stage: _decimal(payment[f"{stage}_received"], f"{stage}_received") for stage in _STAGES}
    for row in rows:
        stage = row.get("stage")
        if stage not in _STAGES or stage in by_stage:
            raise ValueError("existing receipt transaction set is not canonical")
        amount = _decimal(row.get("amount"), "existing amount")
        prior_received[stage] -= amount
        if prior_received[stage] < 0:
            raise ValueError("existing receipt exceeds the persisted summary")
        by_stage[stage] = row
    receivables = {stage: payment[f"{stage}_receivable"] for stage in _STAGES}
    expected = _allocate(receivables, prior_received, credit)
    if expected is None or set(by_stage) != {stage for stage, _ in expected}:
        raise ValueError("existing receipt transaction set is incomplete or conflicting")
    transaction_ids: list[int] = []
    for stage, amount in expected:
        row = by_stage[stage]
        if (int(row.get("client_payment_id")) != int(payment["id"]) or str(row.get("case_no")) != str(payment["case_no"]) or row.get("transaction_type") != "receipt" or row.get("transaction_status") != "succeeded" or _decimal(row.get("amount"), "existing amount") != amount or str(row.get("occurred_at"))[:10] != occurred_at or row.get("external_reference") != f"fp:{fingerprint}:{stage}" or int(row.get("finance_import_row_id")) != finance_import_row_id):
            raise ValueError("existing receipt transaction set is incomplete or conflicting")
        transaction_ids.append(int(row["id"]))
    assert len(transaction_ids) == len(expected)
    return transaction_ids


def reconcile_client_receipt(cursor: Any, finance_import_row_id: int) -> dict[str, Any]:
    """Reconcile one canonical bank row without owning the outer transaction."""
    if not callable(getattr(cursor, "execute", None)):
        raise AssertionError("cursor must provide execute()")
    if isinstance(finance_import_row_id, bool) or not isinstance(finance_import_row_id, int) or finance_import_row_id < 1:
        raise ValueError("finance_import_row_id must be a positive integer")
    cursor.execute("SELECT id, format_id, dedup_fingerprint, direction, credit, classification_type, reconciliation_status, reconciliation_reference, transaction_date, cancellation_code, bank_references FROM finance_import_rows WHERE id = %s FOR UPDATE", (finance_import_row_id,))
    staged = cursor.fetchone()
    if staged is None:
        raise ValueError("finance import row does not exist")
    staged = _mapping(staged, "finance import row")
    fingerprint = staged.get("dedup_fingerprint")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        return _pending("fingerprint_missing_or_invalid")
    credit = _decimal(staged.get("credit"), "credit")
    if staged.get("format_id") not in {"legacy", "sinopac"} or staged.get("direction") != "incoming" or staged.get("classification_type") != "client_receipt" or credit <= 0:
        return _pending("staging_row_not_eligible")
    reconciliation_status = staged.get("reconciliation_status")
    if reconciliation_status not in {"pending", "reconciled"}:
        raise ValueError("finance import row has an unsupported reconciliation status")
    occurred_at = _transaction_date(staged.get("transaction_date"))
    if occurred_at is None:
        return _pending("transaction_date_missing")
    create_snapshot, record_transaction, resolve_virtual_account, lock_lifecycle_command = _dependencies()
    references = _bank_references(staged.get("bank_references"))
    projection_row = dict(staged)
    projection_row["bank_references"] = references
    cancellation_code = resolve_finance_cancellation_code(projection_row)["cancellation_code"]
    resolved = resolve_virtual_account(cursor, cancellation_code)
    if resolved.get("result") != "resolved":
        return _pending(str(resolved.get("reason") or "virtual_account_unresolved"))
    case_no = str(resolved["case_no"])
    evaluation_at = current_business_instant()
    lifecycle_key = f"finance-receipt:{fingerprint}"
    expected_version = _lifecycle_expected_version(cursor, case_no, lifecycle_key)
    command_envelope = lock_lifecycle_command(cursor, case_no, expected_version, lifecycle_key)
    evaluation_at = _replay_evaluation_at(command_envelope, evaluation_at)
    lifecycle_context = {"command_envelope": command_envelope, "evaluation_at": evaluation_at, "actor": _LIFECYCLE_ACTOR, "idempotency_key": lifecycle_key}
    cursor.execute("SELECT o.case_no, o.status, o.service_days, o.service_hours_per_day, c.identity_status, o.floor_fee, o.deposit_date, o.deposit_service_days, o.start_date, o.actual_start_date, o.actual_end_date FROM orders o JOIN clients c ON c.id = o.client_id WHERE o.case_no = %s FOR UPDATE", (case_no,))
    order = cursor.fetchone()
    if order is None:
        return _pending("case_not_found", case_no)
    order = _mapping(order, "order")
    cursor.execute("SELECT id, client_payment_id, case_no, stage, transaction_type, transaction_status, amount, occurred_at, external_reference, finance_import_row_id FROM client_payment_transactions WHERE finance_import_row_id = %s ORDER BY id FOR UPDATE", (finance_import_row_id,))
    existing_rows = [_mapping(row, "existing transaction") for row in cursor.fetchall()]
    if existing_rows:
        if reconciliation_status != "reconciled":
            raise ValueError("pending staging row already has formal receipt transactions")
        payment_ids = {int(row["client_payment_id"]) for row in existing_rows}
        if len(payment_ids) != 1:
            raise ValueError("existing receipt transactions span client payments")
        payment = _load_payment(cursor, payment_ids.pop())
        if str(payment["case_no"]) != case_no:
            raise ValueError("existing receipt transactions resolve to another case")
        transaction_ids = _validate_existing_set(existing_rows, payment=payment, finance_import_row_id=finance_import_row_id, fingerprint=fingerprint, credit=credit, occurred_at=occurred_at)
        deposit_row = next((row for row in existing_rows if row.get("stage") == "deposit"), None)
        if deposit_row is not None:
            replay = record_transaction(cursor, int(payment["id"]), {"stage": "deposit", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": _decimal(deposit_row.get("amount"), "existing amount"), "occurred_at": occurred_at, "external_reference": f"fp:{fingerprint}:deposit", "finance_import_row_id": finance_import_row_id, "reversal_of_transaction_id": None, "notes": None}, lifecycle_context=lifecycle_context)
            if int(replay["transaction_id"]) != int(deposit_row["id"]):
                raise ValueError("deposit lifecycle replay returned another transaction")
        if staged.get("reconciliation_reference") not in {None, f"fp:{fingerprint}"}:
            raise ValueError("staging reconciliation reference conflicts with fingerprint")
        return {"result": "existing", "transaction_ids": transaction_ids, "client_payment_id": int(payment["id"]), "case_no": case_no}
    if reconciliation_status == "reconciled":
        raise ValueError("reconciled staging row has no formal receipt transactions")
    cursor.execute(f"SAVEPOINT {_SAVEPOINT}")
    snapshot_order = {"case_no": case_no, "service_days": order.get("service_days"), "service_hours_per_day": order.get("service_hours_per_day"), "identity_status": order.get("identity_status"), "client_floor_fee": order.get("floor_fee", 0), "actual_start_date": order.get("actual_start_date"), "start_date": order.get("start_date"), "actual_completion_date": order.get("actual_end_date")}
    schedule = {"deposit_service_days": order.get("deposit_service_days"), "deposit_due_date": order.get("deposit_date")}
    try:
        snapshot = create_snapshot(cursor, snapshot_order, schedule)
    except ValueError:
        _rollback_snapshot(cursor)
        return _pending("snapshot_invalid_order_terms", case_no)
    if snapshot.get("result") == "review_required":
        _rollback_snapshot(cursor)
        return _pending(str(snapshot.get("reason") or "snapshot_review_required"), case_no)
    client_payment_id = int(snapshot["payment_id"])
    payment = _load_payment(cursor, client_payment_id)
    if str(payment["case_no"]) != case_no:
        _rollback_snapshot(cursor)
        raise ValueError("client payment snapshot belongs to another case")
    receivables, received = _payment_amounts(payment)
    allocations = _allocate(receivables, received, credit)
    if allocations is None:
        _rollback_snapshot(cursor)
        return _pending("receipt_exceeds_remaining_receivable", case_no)
    cursor.execute(f"RELEASE SAVEPOINT {_SAVEPOINT}")
    transaction_ids = []
    for stage, amount in allocations:
        result = record_transaction(cursor, client_payment_id, {"stage": stage, "transaction_type": "receipt", "transaction_status": "succeeded", "amount": amount, "occurred_at": occurred_at, "external_reference": f"fp:{fingerprint}:{stage}", "finance_import_row_id": finance_import_row_id, "reversal_of_transaction_id": None, "notes": None}, lifecycle_context=lifecycle_context if stage == "deposit" else None)
        transaction_ids.append(int(result["transaction_id"]))
    cursor.execute("UPDATE finance_import_rows SET reconciliation_status = 'reconciled', reconciliation_reference = %s, reconciled_at = CURRENT_TIMESTAMP WHERE id = %s AND reconciliation_status = 'pending'", (f"fp:{fingerprint}", finance_import_row_id))
    if getattr(cursor, "rowcount", 1) != 1:
        raise RuntimeError("staging row reconciliation update failed")
    assert transaction_ids
    return {"result": "reconciled", "transaction_ids": transaction_ids, "client_payment_id": client_payment_id, "case_no": case_no}


__all__ = ["configure_receipt_reconciliation_dependencies", "reconcile_client_receipt"]

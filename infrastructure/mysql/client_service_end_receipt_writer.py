"""Post a verified terminal-case receipt inside the caller's Finance Import transaction."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from infrastructure.mysql.client_receipt_reconciliation_repository import (
    _ALLOCATION_INSERT_SQL,
    _LEDGER_INSERT_SQL,
    _OUTBOX_INSERT_SQL,
    _OVERAGE_REFUND_EVENT_INSERT_SQL,
    _OVERAGE_REFUND_PROJECTION_INSERT_SQL,
    _insert_refund_recipient_snapshot,
    _mark_bank_row_reconciled,
)
from infrastructure.mysql.client_service_end_receipt_preview import (
    ClientServiceEndReceiptPreview,
    LateReceiptOpenBalance,
    preview_client_service_end_receipt,
)
from shared_kernel.identities import ActorContext, IdempotencyKey


@dataclass(frozen=True, slots=True)
class ClientServiceEndReceiptResult:
    ledger_entry_id: int
    account_version: int
    refund_identity: str | None
    allocation_count: int


def terminal_receipt_allocations(
    preview: ClientServiceEndReceiptPreview,
) -> tuple[tuple[LateReceiptOpenBalance, int], ...]:
    """Only consume existing earned balances; never create a receivable to fit cash."""
    receivables = tuple(i for i in preview.open_balances if i.direction == "receivable_from_client")
    previous_cash = preview.balance.net_received_ntd - preview.bank_amount_ntd
    before_due = max(0, preview.service_due_ntd + preview.fee_ntd - previous_cash)
    if sum(i.amount_ntd for i in receivables) != before_due:
        raise ValueError("late_service_end_receipt_open_amount_requires_review")
    if any(i.obligation_type not in {"deposit", "first", "second", "adjustment"} for i in receivables):
        raise ValueError("late_service_end_receipt_open_amount_requires_review")
    stages = {"deposit": 0, "first": 1, "second": 2, "adjustment": 3}
    if len({i.obligation_type for i in receivables}) != len(receivables):
        raise ValueError("late_service_end_receipt_open_amount_requires_review")
    remaining = preview.bank_amount_ntd
    result: list[tuple[LateReceiptOpenBalance, int]] = []
    for item in sorted(receivables, key=lambda i: stages[i.obligation_type]):
        amount = min(item.amount_ntd, remaining)
        if amount:
            result.append((item, amount))
        remaining -= amount
    return tuple(result)


def apply_client_service_end_receipt(
    connection: Any, *, expected: ClientServiceEndReceiptPreview,
    key: IdempotencyKey, actor: ActorContext, reason: str,
) -> ClientServiceEndReceiptResult:
    """The outer correction workflow owns replay, commit and rollback."""
    preview = preview_client_service_end_receipt(
        connection, row_id=expected.row_id, case_no=expected.case_no, lock=True,
    )
    if preview.fingerprint != expected.fingerprint:
        raise ValueError("late_service_end_receipt_preview_stale")
    allocations = terminal_receipt_allocations(preview)
    token = hashlib.sha256(f"sinopac-service-end:{preview.row_id}".encode()).hexdigest()
    child_root = "sinopac-service-end:" + hashlib.sha256(key.value.encode()).hexdigest()
    version = preview.account_version + 1
    refund = f"refund:service-end:{token}" if preview.balance.new_refund_ntd else None
    with connection.cursor() as cursor:
        cursor.execute(
            _LEDGER_INSERT_SQL,
            (preview.case_no, preview.row_id, preview.bank_amount_ntd, preview.transaction_date,
             token, child_root + ":ledger", actor.actor_id, reason),
        )
        entry_id = int(cursor.lastrowid or 0)
        if entry_id <= 0:
            raise RuntimeError("late_service_end_receipt_ledger_missing")
        for ordinal, (item, amount) in enumerate(allocations, start=1):
            cursor.execute(_ALLOCATION_INSERT_SQL, (entry_id, item.identity, amount, ordinal))
            remaining = item.amount_ntd - amount
            cursor.execute(
                "UPDATE client_obligations SET amount_due_ntd=%s,status=%s,projection_version=%s "
                "WHERE case_no=%s AND obligation_identity=%s AND status='open' "
                "AND current_event_id=%s AND amount_due_ntd=%s",
                (remaining, "open" if remaining else "settled", version,
                 preview.case_no, item.identity, item.event_id, item.amount_ntd),
            )
            if cursor.rowcount != 1:
                raise ValueError("late_service_end_receipt_preview_stale")
        if refund is not None:
            source = allocations[-1][0].identity if allocations else None
            surplus = preview.balance.new_refund_ntd
            cursor.execute(
                _OVERAGE_REFUND_EVENT_INSERT_SQL,
                (refund, preview.case_no, surplus, f"sinopac-service-end-ledger:{entry_id}", source,
                 preview.account_version, child_root + ":refund", actor.actor_id, reason),
            )
            refund_event_id = int(cursor.lastrowid or 0)
            if refund_event_id <= 0:
                raise RuntimeError("late_service_end_refund_event_missing")
            cursor.execute(
                _OVERAGE_REFUND_PROJECTION_INSERT_SQL,
                (refund, preview.case_no, source, surplus, refund_event_id, version),
            )
            _insert_refund_recipient_snapshot(cursor, refund, preview.case_no, "amount_correction",
                                              require_complete=False)
        cursor.execute(
            "UPDATE client_finance_accounts SET aggregate_version=%s WHERE case_no=%s AND aggregate_version=%s",
            (version, preview.case_no, preview.account_version),
        )
        if cursor.rowcount != 1:
            raise ValueError("late_service_end_receipt_preview_stale")
        _mark_bank_row_reconciled(cursor, preview.row_id, token)
        snapshot = {
            "ledger_entry_id": entry_id, "bank_row_id": preview.row_id, "refund_identity": refund,
            "cancellation_event_id": preview.cancellation_event_id,
            "service_due_ntd": preview.service_due_ntd, "fee_ntd": preview.fee_ntd,
            **asdict(preview.balance),
        }
        cursor.execute(
            "INSERT INTO client_finance_apply_receipts "
            "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,resulting_account_version,result_snapshot) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (child_root, preview.fingerprint.value, preview.fingerprint.value, preview.case_no, version,
             json.dumps({"late_service_end_receipt": snapshot}, ensure_ascii=False)),
        )
        cursor.execute(
            _OUTBOX_INSERT_SQL,
            (preview.case_no, "projection_refresh", child_root + ":projection",
             json.dumps({"case_no": preview.case_no, "account_version": version}, ensure_ascii=False)),
        )
    return ClientServiceEndReceiptResult(entry_id, version, refund, len(allocations))

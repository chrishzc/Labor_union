"""Canonical MySQL adapter for government-funded recovery of a union advance."""

from __future__ import annotations

from datetime import date

from domains.client_finance.subsidy_advance import SubsidyAdvanceFacts
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.subsidy_advance_recovery import SubsidyAdvanceRecoveryTarget


class MySqlSubsidyAdvanceRecoveryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def find_target(self, event):
        with self._connection.cursor() as cursor:
            cursor.execute(_TARGET_SQL, (event.government_transaction_id, event.claim_item_id))
            rows = tuple(cursor.fetchall())
        if len(rows) != 1:
            return None
        row = rows[0]
        if not isinstance(row["actual_end_date"], date):
            return None
        return SubsidyAdvanceRecoveryTarget(
            f"client-ledger:{int(row['advance_entry_id'])}",
            MoneyNTD(int(row["advance_paid_ntd"])),
            MoneyNTD(int(row["recovered_amount_ntd"])),
            SubsidyAdvanceFacts(
                str(row["case_no"]),
                row["actual_end_date"],
                MoneyNTD(int(row["entitled_amount_ntd"])),
                MoneyNTD(0),
            ),
        )

    def save_recovery(self, event, recovery) -> bool:
        advance_id = _identity_id(recovery.advance_entry_identity, "client-ledger:")
        with self._connection.cursor() as cursor:
            cursor.execute(_ALLOCATION_SQL, (event.government_transaction_id, event.claim_item_id))
            allocation = cursor.fetchone()
            if allocation is None:
                raise RuntimeError("government_subsidy_allocation_not_found")
            cursor.execute(_EXISTING_SQL, (advance_id,))
            if cursor.fetchone() is not None:
                return False
            cursor.execute(_INSERT_SQL, (recovery.case_no, advance_id, int(allocation["id"]), recovery.amount.amount, event.source_outbox_id))
            if cursor.rowcount != 1:
                raise RuntimeError("subsidy_advance_recovery_write_failed")
        return True

    def record_anomaly(self, event, reason: str) -> None:
        payload = '{"reason":"' + reason + '","source_outbox_id":' + str(event.source_outbox_id) + '}'
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) VALUES (%s,'anomaly_review_required',%s,%s)", (event.case_no, f"subsidy-advance-review:{event.source_outbox_id}", payload))


def _identity_id(value: str, prefix: str) -> int:
    raw = value.removeprefix(prefix)
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError("subsidy advance identity is invalid")
    return int(raw)


_TARGET_SQL = """
SELECT ledger.id advance_entry_id,ledger.case_no,ledger.amount_ntd advance_paid_ntd,
       link.entitled_amount_ntd,orders.actual_end_date,
       COALESCE(recovery.recovered_amount_ntd,0) recovered_amount_ntd
FROM government_subsidy_allocations allocation
JOIN client_subsidy_return_claim_item_links link ON link.claim_item_id=allocation.claim_item_id
JOIN client_ledger_obligation_allocations ledger_allocation ON ledger_allocation.obligation_identity=link.obligation_identity
JOIN client_ledger_entries ledger ON ledger.id=ledger_allocation.ledger_entry_id AND ledger.entry_type='subsidy_advance'
JOIN orders ON orders.case_no=ledger.case_no
LEFT JOIN client_subsidy_advance_recoveries recovery ON recovery.advance_ledger_entry_id=ledger.id
WHERE allocation.transaction_id=%s AND allocation.claim_item_id=%s AND allocation.allocation_type='receipt'
"""
_ALLOCATION_SQL = "SELECT id FROM government_subsidy_allocations WHERE transaction_id=%s AND claim_item_id=%s AND allocation_type='receipt' FOR UPDATE"
_EXISTING_SQL = "SELECT id FROM client_subsidy_advance_recoveries WHERE advance_ledger_entry_id=%s FOR UPDATE"
_INSERT_SQL = "INSERT INTO client_subsidy_advance_recoveries(case_no,advance_ledger_entry_id,government_allocation_id,recovered_amount_ntd,source_outbox_id) VALUES (%s,%s,%s,%s,%s)"

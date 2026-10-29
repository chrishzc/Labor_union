"""MySQL adapter for the bounded Client Finance read model.

This adapter only reads canonical Client Finance roots.  It borrows the
request connection and never commits, rolls back, or opens a nested unit of
work.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator

from pymysql.err import OperationalError
from infrastructure.mysql.case_category_query import CASE_CATEGORY_SQL
from subsystems.client_finance.client_payments_query import FinanceCaseCategory

from subsystems.client_finance.client_payments_query import (
    ClientFinanceAllocationFact,
    ClientFinanceCaseQuery,
    ClientFinanceCaseSummary,
    ClientFinanceLedgerEntryFact,
    ClientFinanceObligationFact,
    ClientFinancePageQuery,
)


class ClientFinanceCaseNotFound(ValueError):
    """The requested case has no canonical Client Finance account."""


class MySqlClientFinanceQueryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query_all(self) -> ClientFinancePageQuery:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_CASE_SUMMARY_SQL)
            rows = cursor.fetchall()
        return ClientFinancePageQuery(
            tuple(_summary(row) for row in rows)
        )

    def query_categories(self) -> tuple[FinanceCaseCategory, ...]:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute("SELECT o.case_no," + CASE_CATEGORY_SQL + " AS category "
                           "FROM orders o JOIN clients c ON c.id=o.client_id ORDER BY o.case_no")
            return tuple(FinanceCaseCategory(str(row["case_no"]), row["category"]) for row in cursor.fetchall())

    def query_case(self, case_no: str) -> ClientFinanceCaseQuery:
        normalized = _case_no(case_no)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_ACCOUNT_SQL, (normalized,))
            account = cursor.fetchone()
            if account is None:
                raise ClientFinanceCaseNotFound("client_finance_case_not_found")
            cursor.execute(_OBLIGATIONS_SQL, (normalized,))
            obligation_rows = cursor.fetchall()
            cursor.execute(_LEDGER_SQL, (normalized,))
            ledger_rows = cursor.fetchall()
        return ClientFinanceCaseQuery(
            normalized,
            str(_nonnegative(account["aggregate_version"], "aggregate_version")),
            tuple(_obligation(row) for row in obligation_rows),
            _ledger_entries(ledger_rows),
        )


def _case_no(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("client_finance_case_not_found")
    normalized = value.strip()
    if not normalized or len(normalized) > 50:
        raise ValueError("client_finance_case_not_found")
    return normalized


def _summary(row) -> ClientFinanceCaseSummary:
    outstanding = _nonnegative(row["open_receivable_amount_ntd"], "open_receivable_amount_ntd")
    has_receipts = int(row["net_receipt_amount_ntd"]) > 0 or int(row["historical_paid_count"]) > 0
    receipt_status = (
        "partially_received" if outstanding > 0 and has_receipts else
        "unpaid" if outstanding > 0 else
        "received" if has_receipts else
        "settled" if int(row["receivable_count"]) > 0 else "pending"
    )
    return ClientFinanceCaseSummary(
        str(row["case_no"]),
        str(_nonnegative(row["aggregate_version"], "aggregate_version")),
        _nonnegative(row["open_receivable_amount_ntd"], "open_receivable_amount_ntd"),
        _nonnegative(row["open_payable_amount_ntd"], "open_payable_amount_ntd"),
        _nonnegative(row["obligation_count"], "obligation_count"),
        _nonnegative(row["ledger_entry_count"], "ledger_entry_count"),
        _nonnegative(row["receipt_entry_count"], "receipt_entry_count"),
        receipt_status,
    )


def _obligation(row) -> ClientFinanceObligationFact:
    obligation_type = str(row["obligation_type"])
    direction = str(row["direction"])
    if obligation_type not in {
        "deposit", "first", "second", "refund", "subsidy_return", "adjustment"
    } or direction not in {"receivable_from_client", "payable_to_client"}:
        raise ValueError("client_finance_obligation_invalid")
    status = str(row["status"])
    if status not in {"open", "settled", "cancelled"}:
        raise ValueError("client_finance_obligation_invalid")
    return ClientFinanceObligationFact(
        str(row["obligation_identity"]),
        obligation_type,
        direction,
        _nonnegative(row["amount_due_ntd"], "amount_due_ntd"),
        _date_value(row["due_date"]),
        status,
        str(_nonnegative(row["projection_version"], "projection_version")),
    )


def _ledger_entries(rows) -> tuple[ClientFinanceLedgerEntryFact, ...]:
    entries: dict[int, ClientFinanceLedgerEntryFact] = {}
    allocations: dict[int, list[ClientFinanceAllocationFact]] = {}
    for row in rows:
        entry_id = _positive(row["entry_id"], "entry_id")
        entry_type = str(row["entry_type"])
        if entry_type not in {"receipt", "refund", "adjustment", "reversal", "subsidy_return", "subsidy_advance"}:
            raise ValueError("client_finance_ledger_entry_invalid")
        if entry_id not in entries:
            entries[entry_id] = ClientFinanceLedgerEntryFact(
                entry_id,
                entry_type,
                _positive(row["amount_ntd"], "amount_ntd"),
                _required_date(row["occurred_on"], "occurred_on"),
                str(row["reconciliation_reference"]),
                _optional_positive(row["reversal_of_entry_id"]),
                _datetime_value(row["created_at"]),
                (),
            )
        identity = row.get("allocation_obligation_identity")
        if identity is not None:
            allocations.setdefault(entry_id, []).append(
                ClientFinanceAllocationFact(
                    str(identity),
                    _positive(row["allocation_amount_ntd"], "allocation_amount_ntd"),
                )
            )
    return tuple(
        ClientFinanceLedgerEntryFact(
            entry.entry_id,
            entry.entry_type,
            entry.amount_ntd,
            entry.occurred_on,
            entry.reconciliation_reference,
            entry.reversal_of_entry_id,
            entry.created_at,
            tuple(allocations.get(entry_id, ())),
        )
        for entry_id, entry in entries.items()
    )


def _nonnegative(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"client_finance_{field}_invalid")
    result = int(value)
    if result < 0:
        raise ValueError(f"client_finance_{field}_invalid")
    return result


def _positive(value, field: str) -> int:
    result = _nonnegative(value, field)
    if result <= 0:
        raise ValueError(f"client_finance_{field}_invalid")
    return result


def _optional_positive(value):
    return None if value is None else _positive(value, "reversal_of_entry_id")


def _date_value(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _required_date(value, field: str) -> date:
    result = _date_value(value)
    if result is None:
        raise ValueError(f"client_finance_{field}_invalid")
    return result


def _datetime_value(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError:
        raise


_CASE_SUMMARY_SQL = """
SELECT account.case_no, account.aggregate_version,
       COALESCE(SUM(CASE WHEN obligation.direction='receivable_from_client'
                         AND obligation.status='open'
                         AND historical.obligation_identity IS NULL
                        THEN obligation.amount_due_ntd ELSE 0 END), 0)
           AS open_receivable_amount_ntd,
       COALESCE(SUM(CASE WHEN obligation.direction='payable_to_client'
                         AND obligation.status='open'
                         AND historical.obligation_identity IS NULL
                        THEN obligation.amount_due_ntd ELSE 0 END), 0)
           AS open_payable_amount_ntd,
       COUNT(DISTINCT obligation.obligation_identity) AS obligation_count,
       (SELECT COUNT(*) FROM client_ledger_entries ledger
         WHERE ledger.case_no=account.case_no) AS ledger_entry_count,
       (SELECT COUNT(*) FROM client_ledger_entries receipt
         WHERE receipt.case_no=account.case_no
           AND receipt.entry_type='receipt') AS receipt_entry_count,
       COUNT(CASE WHEN obligation.direction='receivable_from_client'
                   AND obligation.status<>'cancelled' THEN 1 END) AS receivable_count,
       COUNT(CASE WHEN obligation.direction='receivable_from_client'
                   AND obligation.status<>'cancelled'
                   AND historical.confirmation_kind='paid' THEN 1 END) AS historical_paid_count,
       COALESCE((SELECT SUM(CASE WHEN ledger.entry_type='receipt' THEN ledger.amount_ntd
                                WHEN ledger.entry_type='reversal' AND target.entry_type='receipt' THEN -ledger.amount_ntd
                                ELSE 0 END)
          FROM client_ledger_entries ledger
          LEFT JOIN client_ledger_entries target ON target.id=ledger.reversal_of_entry_id AND target.case_no=ledger.case_no
         WHERE ledger.case_no=account.case_no),0) AS net_receipt_amount_ntd
FROM client_finance_accounts account
LEFT JOIN client_obligations obligation
       ON obligation.case_no=account.case_no
LEFT JOIN historical_client_payment_projections historical
       ON historical.obligation_identity=obligation.obligation_identity
      AND historical.amount_snapshot_ntd=obligation.amount_due_ntd
      AND historical.obligation_projection_version=obligation.projection_version
GROUP BY account.case_no, account.aggregate_version
ORDER BY account.case_no
"""

_ACCOUNT_SQL = (
    "SELECT case_no,aggregate_version FROM client_finance_accounts WHERE case_no=%s"
)
_OBLIGATIONS_SQL = (
    "SELECT obligation_identity,obligation_type,direction,amount_due_ntd,due_date,"
    "status,projection_version FROM client_obligations "
    "WHERE case_no=%s ORDER BY obligation_identity"
)
_LEDGER_SQL = (
    "SELECT ledger.id AS entry_id,ledger.entry_type,ledger.amount_ntd,"
    "ledger.occurred_on,ledger.reconciliation_reference,"
    "ledger.reversal_of_entry_id,ledger.created_at,"
    "allocation.obligation_identity AS allocation_obligation_identity,"
    "allocation.amount_ntd AS allocation_amount_ntd "
    "FROM client_ledger_entries ledger LEFT JOIN "
    "client_ledger_obligation_allocations allocation "
    "ON allocation.ledger_entry_id=ledger.id WHERE ledger.case_no=%s "
    "ORDER BY ledger.occurred_on,ledger.id,allocation.allocation_ordinal"
)


__all__ = [
    "ClientFinanceCaseNotFound",
    "MySqlClientFinanceQueryRepository",
]


def query_case_accounting(connection, case_no, *, for_update=False):
    """Project original obligation amounts and effective cash allocations only."""
    from subsystems.client_finance.case_accounting_query import (
        ClientAccountingItem, ClientAccountingTransaction,
    )
    lock = " FOR UPDATE" if for_update else ""
    with connection.cursor() as cursor:
        if for_update:
            cursor.execute("SELECT case_no FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
            cursor.fetchall()
            cursor.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s FOR UPDATE", (case_no,))
            cursor.fetchall()
        cursor.execute(
            "SELECT o.obligation_identity,o.obligation_type,o.direction,o.due_date,o.status,"
            "o.amount_due_ntd,o.projection_version,e.after_amount_ntd,"
            "COALESCE(a.aggregate_version,0) AS account_version,c.name AS client_name,"
            "h.confirmation_kind,h.amount_snapshot_ntd,"
            "h.current_event_id AS historical_event "
            "FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id "
            "JOIN orders r ON r.case_no=o.case_no JOIN clients c ON c.id=r.client_id "
            "LEFT JOIN client_finance_accounts a ON a.case_no=o.case_no "
            "LEFT JOIN historical_client_payment_projections h ON h.obligation_identity=o.obligation_identity "
            "AND h.amount_snapshot_ntd=o.amount_due_ntd AND h.obligation_projection_version=o.projection_version "
            "WHERE o.case_no=%s AND o.status<>'cancelled' "
            "AND o.obligation_type<>'subsidy_return' ORDER BY o.obligation_identity" + lock, (case_no,),
        )
        obligations = cursor.fetchall()
        cursor.execute(
            "SELECT l.id,l.entry_type,l.occurred_on,l.reversal_of_entry_id,"
            "base.entry_type AS reversed_type,x.obligation_identity,x.amount_ntd,b.format_id "
            "FROM client_ledger_entries l JOIN client_ledger_obligation_allocations x ON x.ledger_entry_id=l.id "
            "LEFT JOIN client_ledger_entries base ON base.id=l.reversal_of_entry_id "
            "LEFT JOIN finance_import_rows b ON b.id=l.finance_import_row_id "
            "WHERE l.case_no=%s ORDER BY l.id,x.allocation_ordinal" + lock, (case_no,),
        )
        allocations = cursor.fetchall()
        cursor.execute(
            "SELECT d.receivable_obligation_identity,d.overage_amount_ntd "
            "FROM client_receipt_overage_dispositions d WHERE d.case_no=%s "
            "AND NOT EXISTS(SELECT 1 FROM client_ledger_entries r WHERE r.reversal_of_entry_id=d.receipt_ledger_entry_id)" + lock,
            (case_no,),
        )
        overages = cursor.fetchall()
        cursor.execute(
            "SELECT recovery.refund_obligation_identity AS receivable_obligation_identity,"
            "event.after_amount_ntd AS overage_amount_ntd "
            "FROM client_over_refund_recoveries recovery "
            "JOIN client_over_refund_recovery_events event ON event.recovery_identity=recovery.recovery_identity "
            "AND event.event_type='established' WHERE recovery.case_no=%s "
            "AND NOT EXISTS (SELECT 1 FROM client_ledger_entries reversal "
            "WHERE reversal.reversal_of_entry_id=recovery.refund_ledger_entry_id)" + lock,
            (case_no,),
        )
        refund_overages = cursor.fetchall()
    sums, transactions = {}, []
    for row in allocations:
        kind = row["entry_type"]
        if kind not in {"receipt", "refund", "reversal"}:
            continue
        if kind == "reversal" and row["reversed_type"] not in {"receipt", "refund"}:
            continue
        identity = row["obligation_identity"]
        amount = int(row["amount_ntd"]) * (-1 if kind == "reversal" else 1)
        sums[identity] = sums.get(identity, 0) + amount
        transactions.append(ClientAccountingTransaction(
            f"client-entry:{row['id']}:{identity}", identity, str(row["occurred_on"]), kind,
            amount, row["format_id"],
        ))
    allocated = dict(sums)
    for row in (*overages, *refund_overages):
        identity = row["receivable_obligation_identity"]
        sums[identity] = sums.get(identity, 0) + int(row["overage_amount_ntd"])
    labels = {"deposit": "訂金", "first": "第一期", "second": "第二期", "refund": "客戶退款", "adjustment": "帳務調整"}
    items = []
    for row in obligations:
        identity = row["obligation_identity"]
        # Client obligations are remaining-balance projections, including after
        # date-only owner events. Nominal amount is remaining plus effective
        # allocated cash; explicit surplus is displayed only in actual cash.
        expected = int(row["amount_due_ntd"]) + allocated.get(identity, 0)
        paid = sums.get(identity, 0)
        if row["confirmation_kind"] == "paid":
            paid += int(row["amount_snapshot_ntd"])
        items.append(ClientAccountingItem(
            identity, "receivable" if row["direction"] == "receivable_from_client" else "payable",
            labels.get(row["obligation_type"], "帳務款項"), str(row["client_name"]), expected,
            paid, identity in sums or row["confirmation_kind"] == "paid",
            f"{row['account_version']}:{row['projection_version']}:{row['historical_event'] or 0}",
            None if row["due_date"] is None else str(row["due_date"]),
        ))
    valid = {item.identity for item in items}
    return tuple(items), tuple(row for row in transactions if row.item_identity in valid)

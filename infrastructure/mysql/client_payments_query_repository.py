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
    return ClientFinanceCaseSummary(
        str(row["case_no"]),
        str(_nonnegative(row["aggregate_version"], "aggregate_version")),
        _nonnegative(row["open_receivable_amount_ntd"], "open_receivable_amount_ntd"),
        _nonnegative(row["open_payable_amount_ntd"], "open_payable_amount_ntd"),
        _nonnegative(row["obligation_count"], "obligation_count"),
        _nonnegative(row["ledger_entry_count"], "ledger_entry_count"),
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
        if entry_type not in {"receipt", "refund", "adjustment", "reversal"}:
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
                        THEN obligation.amount_due_ntd ELSE 0 END), 0)
           AS open_receivable_amount_ntd,
       COALESCE(SUM(CASE WHEN obligation.direction='payable_to_client'
                         AND obligation.status='open'
                        THEN obligation.amount_due_ntd ELSE 0 END), 0)
           AS open_payable_amount_ntd,
       COUNT(DISTINCT obligation.obligation_identity) AS obligation_count,
       (SELECT COUNT(*) FROM client_ledger_entries ledger
         WHERE ledger.case_no=account.case_no) AS ledger_entry_count
FROM client_finance_accounts account
LEFT JOIN client_obligations obligation
       ON obligation.case_no=account.case_no
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

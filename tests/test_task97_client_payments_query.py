from datetime import date, datetime
import inspect

import pytest

from api.routes import client_payments
from infrastructure.mysql.client_payments_query_repository import (
    ClientFinanceCaseNotFound,
    MySqlClientFinanceQueryRepository,
)


class _Cursor:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query
        self.calls = []
        self._rows = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        for marker, rows in self.rows_by_query:
            if marker in sql:
                self._rows = rows
                return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return tuple(self._rows)


class _Connection:
    def __init__(self, rows_by_query):
        self.cursor_instance = _Cursor(rows_by_query)

    def cursor(self):
        return self.cursor_instance


def test_case_query_reads_canonical_roots_and_groups_allocations():
    connection = _Connection(
        [
            ("FROM client_finance_accounts WHERE", [{"case_no": "C-1", "aggregate_version": 3}]),
            (
                "FROM client_obligations",
                [
                    {
                        "obligation_identity": "obligation:C-1:deposit",
                        "obligation_type": "deposit",
                        "direction": "receivable_from_client",
                        "amount_due_ntd": 0,
                        "due_date": date(2026, 8, 1),
                        "status": "settled",
                        "projection_version": 3,
                    }
                ],
            ),
            (
                "FROM client_ledger_entries",
                [
                    {
                        "entry_id": 7,
                        "entry_type": "receipt",
                        "amount_ntd": 1000,
                        "occurred_on": date(2026, 7, 1),
                        "reconciliation_reference": "client-finance:receipt-7",
                        "reversal_of_entry_id": None,
                        "created_at": datetime(2026, 7, 1, 12, 0),
                        "allocation_obligation_identity": "obligation:C-1:deposit",
                        "allocation_amount_ntd": 1000,
                    },
                    {
                        "entry_id": 7,
                        "entry_type": "receipt",
                        "amount_ntd": 1000,
                        "occurred_on": date(2026, 7, 1),
                        "reconciliation_reference": "client-finance:receipt-7",
                        "reversal_of_entry_id": None,
                        "created_at": datetime(2026, 7, 1, 12, 0),
                        "allocation_obligation_identity": "obligation:C-1:second",
                        "allocation_amount_ntd": 200,
                    },
                ],
            ),
        ]
    )

    result = MySqlClientFinanceQueryRepository(connection).query_case(" C-1 ")

    assert result.case_no == "C-1"
    assert result.account_version == "3"
    assert len(result.ledger_entries) == 1
    assert [item.amount_ntd for item in result.ledger_entries[0].allocations] == [1000, 200]
    assert all("SELECT *" not in sql for sql, _ in connection.cursor_instance.calls)
    assert all("client_payments" not in sql for sql, _ in connection.cursor_instance.calls)


def test_case_query_fails_closed_when_canonical_account_is_missing():
    connection = _Connection([("FROM client_finance_accounts WHERE", [])])

    with pytest.raises(ClientFinanceCaseNotFound, match="client_finance_case_not_found"):
        MySqlClientFinanceQueryRepository(connection).query_case("C-404")


def test_client_payments_routes_are_authenticated_and_not_connection_owners():
    source = inspect.getsource(client_payments)
    assert "get_connection" not in source
    assert "SELECT *" not in source
    assert "response_model=BaseResponse[ClientFinancePageView]" in source
    assert "response_model=BaseResponse[ClientFinanceCaseView]" in source
    assert "Dict[str, Any]" not in source
    assert "List[Dict" not in source
    assert "Depends(require_admin)" in source

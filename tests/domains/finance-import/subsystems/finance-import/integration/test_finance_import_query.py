from datetime import datetime
from decimal import Decimal

import pytest

from subsystems.finance_import.query import (
    FinanceImportQueryNotFound,
    FinanceImportQueryService,
    _batch_summary,
    _integer_money,
    _review_row,
)


class _Cursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_arguments: object) -> None:
        return None

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.calls.append((statement, params))

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_instance = cursor

    def cursor(self) -> _Cursor:
        return self.cursor_instance


def test_list_batches_preserves_summary_and_page_contract() -> None:
    cursor = _Cursor([_summary_row()])
    batches = FinanceImportQueryService(_Connection(cursor)).list_batches(
        limit=1, before_batch_id=9
    )

    assert batches == (_batch_summary(_summary_row()),)
    assert cursor.calls[0][1] == (9, 9, 1)
    assert "LEFT JOIN finance_import_batch_contracts" in cursor.calls[0][0]


def test_review_rows_require_formal_batch_and_preserve_query_params() -> None:
    cursor = _Cursor([{"batch_exists": 1}])
    service = FinanceImportQueryService(_Connection(cursor))
    service._fetch_review_rows = lambda _params: (_review_row_source(),)  # type: ignore[method-assign]

    rows = service.list_review_rows(" batch-1 ", limit=10, after_row_id=4)

    assert rows[0].row_identity == "finance-import-row:17"
    assert cursor.calls[0][1] == ("batch-1",)


def test_review_row_query_uses_a_non_reserved_table_alias() -> None:
    cursor = _Cursor([])

    FinanceImportQueryService(_Connection(cursor))._fetch_review_rows(
        ("batch-1", None, None, "manual_review", "business_pending", "blocked", 10)
    )

    statement = cursor.calls[0][0]
    assert "JOIN finance_import_rows finance_row" in statement
    assert "finance_row.id" in statement
    assert " row.id" not in statement


def test_query_rejects_missing_formal_batch() -> None:
    with pytest.raises(FinanceImportQueryNotFound):
        FinanceImportQueryService(_Connection(_Cursor([]))).list_reprocess_runs(
            "batch-1", limit=1
        )


@pytest.mark.parametrize("value", [Decimal("1.5"), Decimal("0"), None])
def test_review_amount_requires_positive_integer_ntd(value: Decimal | None) -> None:
    with pytest.raises(ValueError, match="positive integer NTD"):
        _integer_money({"debit": value, "credit": None})


def test_review_row_parses_json_actions_and_credit_precedence() -> None:
    summary = _review_row(_review_row_source())

    assert summary.amount_ntd == 200
    assert summary.available_actions == ("apply", "ignore")


def _summary_row() -> dict[str, object]:
    return {
        "batch_id": 7,
        "batch_identity": "batch-7",
        "format_id": "sinopac",
        "source_file": r"C:\imports\statement.xlsx",
        "row_count": 3,
        "status": "completed",
        "batch_version": 2,
        "created_at": datetime(2026, 8, 3),
    }


def _review_row_source() -> dict[str, object]:
    return {
        "row_id": 17,
        "transaction_date": None,
        "direction": "credit",
        "debit": Decimal("100"),
        "credit": Decimal("200"),
        "classification_type": "staff_payout",
        "disposition": "manual_review",
        "reconciliation_status": "pending",
        "source_sheet": "Sheet1",
        "source_row": 8,
        "occurrence_count": 1,
        "available_actions": '["apply", "ignore"]',
        "created_at": datetime(2026, 8, 3),
    }

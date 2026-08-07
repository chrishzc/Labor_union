from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from domains.finance_import.planning import FinanceClassificationType
from infrastructure.mysql.historical_reprocess_repository import (
    _ROWS_SQL,
    _normalized_row,
    _target_identities,
)


def test_repository_normalizes_mysql_json_columns_before_classification():
    row = {
        "format_id": "taishin", "source_file": "a.xlsx", "source_bank_account": None,
        "sheet_name": "Sheet1", "source_row": 2, "source_reference": None,
        "transaction_date": "2026-08-01", "transaction_time": None,
        "posting_date": None, "value_date": None, "debit": Decimal("0"),
        "credit": Decimal("300"), "direction": "incoming", "balance": None,
        "currency": "TWD", "summary": None, "memo": None,
        "counterparty_name": None, "counterparty_account": None,
        "cancellation_code": None, "bank_references": "{}", "warnings": "[]",
        "raw_payload": "{}",
    }

    normalized = _normalized_row(row)

    assert normalized["bank_references"] == {}
    assert normalized["warnings"] == []


def test_repository_normalizes_mysql_date_and_time_values_to_the_row_contract():
    row = {
        "format_id": "taishin", "source_file": "a.xlsx", "source_bank_account": None,
        "sheet_name": "Sheet1", "source_row": 2, "source_reference": None,
        "transaction_date": date(2026, 8, 1), "transaction_time": time(9, 8, 7),
        "posting_date": date(2026, 8, 1), "value_date": None, "debit": Decimal("300"),
        "credit": Decimal("0"), "direction": "outgoing", "balance": None,
        "currency": "TWD", "summary": None, "memo": None,
        "counterparty_name": None, "counterparty_account": None,
        "cancellation_code": None, "bank_references": "{}", "warnings": "[]",
        "raw_payload": "{}",
    }

    normalized = _normalized_row(row)

    assert normalized["transaction_date"] == "2026-08-01"
    assert normalized["transaction_time"] == "09:08:07"


def test_repository_normalizes_mysql_timedelta_time_to_the_row_contract():
    from infrastructure.mysql.historical_reprocess_repository import _iso_value

    assert _iso_value(timedelta(hours=9, minutes=8, seconds=7)) == "09:08:07"


def test_repository_refuses_to_guess_a_government_subsidy_target():
    with pytest.raises(ValueError, match="target_required"):
        _target_identities(FinanceClassificationType.GOVERNMENT_SUBSIDY, [1])


def test_repository_uses_a_nonreserved_alias_for_live_mysql_compatibility():
    assert "finance_import_rows bank_row" in _ROWS_SQL
    assert "SELECT row.*" not in _ROWS_SQL

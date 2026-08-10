from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from domains.finance_import.planning import FinanceClassificationType
from infrastructure.mysql.historical_reprocess_repository import (
    _ROWS_SQL,
    _manual_owner_row,
    _normalized_row,
    _target_identities,
    _validate_owner_selections,
)
from subsystems.finance_import.historical_reprocess_workflow import HistoricalOwnerSelection


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


def test_manual_owner_selection_is_optional_and_can_cover_only_ambiguous_rows():
    rows = ({"id": 1}, {"id": 2})
    selection = HistoricalOwnerSelection(
        "finance-import-row:2",
        "C-1",
        "refund:C-1",
        "reviewed by finance",
        ("review:2",),
    )

    _validate_owner_selections(rows, ())
    _validate_owner_selections(rows, (selection,))


def test_manual_owner_selection_rejects_a_row_outside_the_reprocess_batch():
    selection = HistoricalOwnerSelection(
        "finance-import-row:2",
        "C-1",
        "refund:C-1",
        "reviewed by finance",
        ("review:2",),
    )

    with pytest.raises(ValueError, match="not_eligible"):
        _validate_owner_selections(({"id": 1},), (selection,))


def test_manual_owner_candidate_fingerprint_includes_obligation_projection_version():
    selection = HistoricalOwnerSelection(
        "finance-import-row:1",
        "C-1",
        "refund:C-1",
        "reviewed by finance",
        ("review:1",),
    )
    row = {"id": 1, "canonical_fact_version": 0, "credit": Decimal("300")}

    first = _manual_owner_row(_OpenObligationCursor(0), row, selection)
    second = _manual_owner_row(_OpenObligationCursor(1), row, selection)

    assert first.after.decision_facts_fingerprint != second.after.decision_facts_fingerprint


class _OpenObligationCursor:
    def __init__(self, projection_version):
        self._projection_version = projection_version

    def execute(self, _query, _values):
        return None

    def fetchone(self):
        return {"projection_version": self._projection_version}

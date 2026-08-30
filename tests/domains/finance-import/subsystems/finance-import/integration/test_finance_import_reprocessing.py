from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from subsystems.finance_import import reprocessing


def _normalized_row() -> dict[str, object]:
    return {
        "format_id": "taishin", "source_file": "source.xlsx", "source_bank_account": None,
        "sheet_name": "Sheet1", "source_row": 2, "source_reference": None,
        "transaction_date": date(2026, 8, 1), "transaction_time": time(8, 3, 1, 900),
        "posting_date": "2026-08-01", "value_date": None, "debit": Decimal("0"),
        "credit": Decimal("100"), "direction": "incoming", "balance": None,
        "currency": None, "summary": None, "memo": None, "counterparty_name": None,
        "counterparty_account": None, "cancellation_code": None, "bank_references": {},
        "warnings": [], "raw_payload": {}, "dedup_fingerprint": "a" * 64,
    }


def test_normalized_row_canonicalizes_database_values() -> None:
    normalized = reprocessing._normalized_row(_normalized_row())
    assert normalized["transaction_date"] == "2026-08-01"
    assert normalized["transaction_time"] == "08:03:01"


def test_normalized_row_rejects_invalid_fingerprint() -> None:
    row = _normalized_row()
    row["dedup_fingerprint"] = "invalid"
    with pytest.raises(ValueError, match="canonical row fingerprint"):
        reprocessing._normalized_row(row)


def test_plan_fingerprint_is_deterministic_and_database_bound() -> None:
    plans = [{"row_id": 1, "before": {"classification_reason": "old"}, "after": {"classification_reason": "new"}}]
    first = reprocessing._plan_fingerprint({"database": "one", "server": "db"}, 9, plans)
    assert first == reprocessing._plan_fingerprint({"database": "one", "server": "db"}, 9, plans)
    assert first != reprocessing._plan_fingerprint({"database": "two", "server": "db"}, 9, plans)


def test_apply_path_is_retired_before_opening_a_connection() -> None:
    with pytest.raises(ValueError, match="legacy_finance_import_reprocess_apply_retired"):
        reprocessing.reprocess_finance_import_batch(
            1,
            dry_run=False,
            connection_factory=lambda: pytest.fail("must not connect"),
        )


def test_identity_ids_reject_boolean_even_though_bool_is_an_int() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        reprocessing._identity_ids("[true]", "matched_identity_ids")

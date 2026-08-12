"""Append-only MySQL proof for canonical Finance Import staging and deduplication."""

from __future__ import annotations

from decimal import Decimal
import os
from uuid import uuid4

import pytest


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_raw_bank_roots_create_one_canonical_row_and_two_occurrences() -> None:
    from domains.finance_import.transaction_fingerprint import build_dedup_fingerprint
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.finance_import.staging import stage_finance_rows

    token = uuid4().hex
    first = _normalized_row(token, 17)
    second = _normalized_row(token, 18)
    fingerprint = build_dedup_fingerprint(first)
    connection = get_connection()
    try:
        before = _formal_output_counts(connection)
        with connection.cursor() as cursor:
            first_result = stage_finance_rows(cursor, _batch(first), _identity_maps())
            second_result = stage_finance_rows(cursor, _batch(second), _identity_maps())
        connection.commit()
        _assert_staged_result(first_result, second_result, fingerprint)
        _assert_canonical_dedup(connection, fingerprint)
        assert _formal_output_counts(connection) == before
    finally:
        connection.close()


def _batch(row: dict[str, object]) -> dict[str, object]:
    return {"format_id": "taishin", "sheet_name": "交易明細", "header_row": 2, "normalized_rows": [row]}


def _identity_maps() -> dict[str, object]:
    return {"client_refund_accounts": {}, "staff_accounts": {}}


def _normalized_row(token: str, source_row: int) -> dict[str, object]:
    amount = Decimal(1_000 + int(token[:8], 16) % 1_000_000)
    return {
        "format_id": "taishin", "source_file": f"lu-test-finance-{token}.xlsx",
        "source_bank_account": "LU-TEST", "sheet_name": "交易明細", "source_row": source_row,
        "source_reference": None, "transaction_date": "2026-08-10", "transaction_time": "09:08:07",
        "posting_date": "2026-08-10", "value_date": None, "debit": amount,
        "credit": None, "direction": "outgoing", "balance": amount + Decimal("9000.00"), "currency": "TWD",
        "summary": "LU test raw bank root", "memo": "unmatched controlled fixture", "counterparty_name": None,
        "counterparty_account": f"NO-MATCH-{token}", "cancellation_code": None,
        "bank_references": {"fixture": token}, "warnings": [], "raw_payload": {"fixture": token},
    }


def _assert_staged_result(first: dict[str, object], second: dict[str, object], fingerprint: str) -> None:
    first_row = first["staged_rows"][0]
    second_row = second["staged_rows"][0]
    assert first_row["result"] == "inserted"
    assert second_row["result"] == "skipped_existing"
    assert first_row["dedup_fingerprint"] == second_row["dedup_fingerprint"] == fingerprint
    assert first_row["classification_type"] == second_row["classification_type"] == "non_business_review"
    assert first_row["reconciliation_status"] == second_row["reconciliation_status"] == "pending"


def _assert_canonical_dedup(connection, fingerprint: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,classification_type,reconciliation_status FROM finance_import_rows WHERE dedup_fingerprint=%s", (fingerprint,))
        row = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS count FROM finance_import_occurrences WHERE finance_import_row_id=%s", (row["id"],))
        occurrence_count = cursor.fetchone()["count"]
    assert row["classification_type"] == "non_business_review"
    assert row["reconciliation_status"] == "pending"
    assert occurrence_count == 2


def _formal_output_counts(connection) -> tuple[int, int, int]:
    tables = ("client_ledger_entries", "staff_payout_events", "government_subsidy_transactions")
    with connection.cursor() as cursor:
        counts = []
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
            counts.append(int(cursor.fetchone()["count"]))
    return tuple(counts)

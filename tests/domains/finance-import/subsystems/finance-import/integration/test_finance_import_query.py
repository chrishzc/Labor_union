from datetime import datetime
from decimal import Decimal
import sqlite3

import pytest

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportBatchFacts,
    FinanceImportDisposition,
    build_finance_import_plan,
)
from infrastructure.mysql.finance_import_repository import (
    _preview_disposition,
    _sort_canonical_rows,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
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
        ("batch-1", None, None, "manual_review", "business_pending", "blocked", "create", 10)
    )

    statement = cursor.calls[0][0]
    assert "JOIN finance_import_rows finance_row" in statement
    assert "finance_row.id" in statement
    assert " row.id" not in statement


def test_review_rows_and_manifest_share_the_complete_unposted_scope() -> None:
    cursor = _Cursor([])
    service = FinanceImportQueryService(_Connection(cursor))
    service._fetch_review_rows(
        ("batch-1", None, None, "manual_review", "business_pending", "blocked", "create", 10)
    )
    service._fetch_manifest("batch-1")
    for statement, _ in cursor.calls:
        assert "client_legacy_virtual_accounts" not in statement
        assert "JOIN orders" not in statement
        assert "finance_import_source_review_occurrences" not in statement
        for owner in ("client_ledger_entries", "staff_payout_events",
                      "finance_import_reconciliation_receipts",
                      "government_subsidy_period_entries", "finance_import_dispatch_events"):
            assert owner in statement


def test_unmatched_and_blocked_rows_remain_visible_until_formal_posting() -> None:
    database = sqlite3.connect(':memory:')
    database.row_factory = sqlite3.Row
    database.executescript("""
        CREATE TABLE finance_import_batches (
            id INTEGER PRIMARY KEY, format_id TEXT, source_file TEXT, sheet_name TEXT,
            header_row INTEGER, row_count INTEGER, status TEXT, created_at TEXT, completed_at TEXT
        );
        CREATE TABLE finance_import_batch_contracts (
            batch_id INTEGER, batch_identity TEXT, batch_version INTEGER,
            source_content_digest TEXT, classifier_version TEXT, fingerprint_version TEXT
        );
        CREATE TABLE finance_import_rows (
            id INTEGER PRIMARY KEY, transaction_date TEXT, direction TEXT, format_id TEXT,
            debit INTEGER, credit INTEGER, reconciliation_status TEXT, created_at TEXT
        );
        CREATE TABLE finance_import_classification_events (
            id INTEGER PRIMARY KEY, batch_id INTEGER, finance_import_row_id INTEGER,
            classification_version INTEGER, classification_type TEXT, disposition TEXT,
            available_actions TEXT
        );
        CREATE TABLE finance_import_occurrences (
            id INTEGER PRIMARY KEY, batch_id INTEGER, finance_import_row_id INTEGER,
            sheet_name TEXT, source_row INTEGER
        );
        CREATE TABLE client_ledger_entries (finance_import_row_id INTEGER);
        CREATE TABLE staff_payout_events (finance_import_row_id INTEGER);
        CREATE TABLE finance_import_reconciliation_receipts (id INTEGER PRIMARY KEY, finance_import_row_id INTEGER);
        CREATE TABLE government_subsidy_period_entries (finance_import_row_id INTEGER);
        CREATE TABLE finance_import_dispatch_events (batch_id INTEGER, finance_import_row_id INTEGER, outcome TEXT);
        INSERT INTO finance_import_batches VALUES (1,'legacy','test.xlsx','來源',1,10,'previewed','2026-10-30',NULL);
        INSERT INTO finance_import_batch_contracts VALUES (1,'batch-1',1,'digest','v1','v1');
    """)
    for identity in range(1, 11):
        classification = 'non_business_review' if identity == 1 else 'staff_payout' if identity == 10 else 'client_receipt'
        disposition = 'manual_review' if identity == 1 else 'blocked' if identity == 3 else 'create' if identity == 9 else 'business_pending'
        database.execute("INSERT INTO finance_import_rows VALUES (?,'2026-10-30','incoming','legacy',NULL,100,'unmatched','2026-10-30')", (identity,))
        database.execute('INSERT INTO finance_import_classification_events VALUES (?,1,?,0,?,?,?)', (identity, identity, classification, disposition, '[]'))
        database.execute("INSERT INTO finance_import_occurrences VALUES (?,1,?,'來源',?)", (identity, identity, identity + 1))
    database.executescript("""
        INSERT INTO client_ledger_entries VALUES (4);
        INSERT INTO staff_payout_events VALUES (5);
        INSERT INTO finance_import_reconciliation_receipts VALUES (1,6);
        INSERT INTO government_subsidy_period_entries VALUES (7);
        INSERT INTO finance_import_dispatch_events VALUES (1,8,'reconciled');
    """)

    class Cursor:
        def __enter__(self):
            self.cursor = database.cursor()
            return self

        def __exit__(self, *_arguments):
            self.cursor.close()

        def execute(self, statement, parameters):
            self.cursor.execute(statement.replace('%s', '?'), parameters)

        def fetchall(self):
            return [dict(row) for row in self.cursor.fetchall()]

        def fetchone(self):
            row = self.cursor.fetchone()
            return None if row is None else dict(row)

    class Connection:
        def cursor(self):
            return Cursor()

    try:
        service = FinanceImportQueryService(Connection())
        rows = service.list_review_rows('batch-1', limit=100)
        assert [row.row_id for row in rows] == [1, 2, 3, 9, 10]
        assert {row.disposition for row in rows} == {'manual_review', 'business_pending', 'blocked', 'create'}
        assert service.get_manifest('batch-1').review_count == len(rows)
        assert [row.row_id for row in service.list_review_rows('batch-1', limit=2, after_row_id=2)] == [3, 9]
        database.execute('INSERT INTO client_ledger_entries VALUES (2)')
        assert service.get_manifest('batch-1').review_count == 4
        assert [row.row_id for row in service.list_review_rows('batch-1', limit=100)] == [1, 3, 9, 10]
    finally:
        database.close()


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


def test_replayed_manual_review_row_preserves_ready_rows_for_apply() -> None:
    manual_review = _preview_disposition(
        {
            "canonical_batch_id": 4,
            "disposition": "manual_review",
            "latest_dispatch_outcome": "reconciled",
        },
        FinanceClassificationType.NON_BUSINESS_REVIEW,
        9,
    )
    review_row = CanonicalFinanceImportRow(
        "finance-import-row:4",
        0,
        MoneyNTD(100),
        FinanceClassificationType.NON_BUSINESS_REVIEW,
        manual_review,
        PreviewFingerprint("a" * 64),
        evidence=("counterparty_account_no_match",),
        available_actions=("preview_manual_correction",),
    )
    ready_row = CanonicalFinanceImportRow(
        "finance-import-row:5",
        0,
        MoneyNTD(200),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.CREATE,
        PreviewFingerprint("b" * 64),
        target_identities=("client:5",),
        evidence=("exact_virtual_account",),
        available_actions=("preview_apply",),
    )

    plan = build_finance_import_plan(
        FinanceImportBatchFacts(
            "finance-import-batch:9",
            0,
            2,
            1,
            1,
            "c" * 64,
            "classifier-v1",
            "fingerprint-v1",
            (review_row, ready_row),
        )
    )

    assert manual_review is FinanceImportDisposition.MANUAL_REVIEW
    assert plan.apply_allowed is True
    assert tuple(row.row_identity for row in plan.dispatchable_rows) == (
        "finance-import-row:5",
    )


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("reconciled", FinanceImportDisposition.EXISTING),
        ("existing", FinanceImportDisposition.EXISTING),
        ("pending", FinanceImportDisposition.BUSINESS_PENDING),
        ("rejected", FinanceImportDisposition.BUSINESS_PENDING),
        ("conflict", FinanceImportDisposition.BUSINESS_PENDING),
    ],
)
def test_business_dispatch_projection_preserves_terminal_outcome_meaning(
    outcome: str,
    expected: FinanceImportDisposition,
) -> None:
    disposition = _preview_disposition(
        {
            "canonical_batch_id": 9,
            "disposition": "business_pending",
            "latest_dispatch_outcome": outcome,
        },
        FinanceClassificationType.CLIENT_RECEIPT,
        9,
    )

    assert disposition is expected


def test_manually_reconciled_rows_are_existing_when_original_batch_is_replayed():
    assert _preview_disposition(
        {'canonical_batch_id': 5, 'disposition': 'create',
         'latest_dispatch_outcome': None, 'has_reconciliation_receipt': 1},
        FinanceClassificationType.CLIENT_RECEIPT, 5,
    ) is FinanceImportDisposition.EXISTING


def test_an_unposted_bank_fact_from_another_workbook_stays_pending():
    assert _preview_disposition(
        {'canonical_batch_id': 5, 'disposition': 'business_pending',
         'latest_dispatch_outcome': None, 'has_reconciliation_receipt': 0},
        FinanceClassificationType.CLIENT_SUBSIDY_RETURN, 9,
    ) is FinanceImportDisposition.BUSINESS_PENDING


def test_canonical_rows_follow_the_textual_identity_order_required_by_preview() -> None:
    row_ten = CanonicalFinanceImportRow(
        "finance-import-row:10",
        0,
        MoneyNTD(100),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("d" * 64),
    )
    row_two = CanonicalFinanceImportRow(
        "finance-import-row:2",
        0,
        MoneyNTD(200),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("e" * 64),
    )

    ordered = _sort_canonical_rows((row_two, row_ten))

    assert tuple(row.row_identity for row in ordered) == (
        "finance-import-row:10",
        "finance-import-row:2",
    )


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

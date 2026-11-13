"""
File: test_finance_import_query.py
Description: 驗證銀行流水查詢、預覽處置映射與待核對交易對象及關聯案件補齊契約。
"""
from datetime import datetime
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

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
from shared_kernel.durable_job_queue import TerminalDurableJobError
from shared_kernel.identities import CorrelationId
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.import_workflow import FinanceDispatchOutcome, FinanceImportDispatchResult, _validate_dispatch_results
from subsystems.jobs.contracts import DurableJobFailureOutcome
from subsystems.finance_import.query import (
    FinanceImportQueryNotFound,
    FinanceImportQueryService,
    _batch_summary,
    _enrich_bank_transactions,
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
        evidence=("sinopac_staff_account_no_match",),
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


def test_rejected_dispatch_carries_only_its_row_reason_into_the_failed_job(monkeypatch):
    from api.dependencies import finance_import
    from api.dependencies.durable_job_handlers import finance_import_batch_apply_handler
    from infrastructure.mysql import mysql_adapter

    rejected_row = "finance-import-row:17"
    other_row = "finance-import-row:18"
    results = (
        FinanceImportDispatchResult(rejected_row, FinanceDispatchOutcome.REJECTED, reason_code="staff_bank_account_ambiguous"),
        FinanceImportDispatchResult(other_row, FinanceDispatchOutcome.RECONCILED, "staff-payables:proof"),
    )
    plan = SimpleNamespace(dispatchable_rows=tuple(SimpleNamespace(row_identity=row) for row in (rejected_row, other_row)))
    monkeypatch.setattr(mysql_adapter, "get_connection", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(finance_import, "build_finance_import_application", lambda *_: SimpleNamespace(
        apply_batch=lambda request: _validate_dispatch_results(plan, results, request),
    ))
    payload = {
        "batch_identity": "finance-import-batch:1", "expected_batch_version": 0,
        "preview_fingerprint": "a" * 64, "idempotency_key": "test-import",
        "actor": "test", "reason": "", "correlation_id": CorrelationId("test-import").value,
    }

    with pytest.raises(TerminalDurableJobError) as raised:
        finance_import_batch_apply_handler(payload)

    error = DurableJobFailureOutcome.from_typed_error(raised.value.error).to_payload()["error"]
    assert error["code"] == "dispatch_rejected"
    assert error["domain_blockers"] == ["dispatch_rejected", f"{rejected_row}:staff_bank_account_ambiguous"]


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


class _EnrichCursor:
    def __init__(self, receipt_rows=None) -> None:
        self.receipt_rows = receipt_rows if receipt_rows is not None else [
            {"obligation_identity": "receipt:first", "due_date": "2026-10-19", "amount_due_ntd": 6200},
        ]
        self._rows: list[dict[str, object]] = []
        self._one: dict[str, object] | None = None

    def execute(self, statement: str, params=()) -> None:
        sql = " ".join(statement.split())
        if "SELECT name FROM clients WHERE id=%s" in sql:
            self._one = {"name": "林小美"} if params == (7,) else None
        elif "SELECT name FROM staff WHERE id=%s" in sql:
            self._one = {"name": "陳月嫂"} if params == (19,) else None
        elif "SELECT c.name FROM orders o JOIN clients c" in sql:
            self._one = {"name": "林小美"} if params == ("115000001",) else None
        elif "FROM client_legacy_virtual_accounts mapping" in sql:
            self._rows = [{"case_no": "115000001"}] if params == ("99781699115001",) else []
        elif "SELECT obligation_identity, due_date, amount_due_ntd FROM client_obligations" in sql:
            self._rows = self.receipt_rows
        elif "FROM staff_obligations" in sql:
            self._rows = [{"case_no": "115000009", "obligation_identity": "staff:payout", "due_date": "2026-10-19", "amount_due_ntd": 12000}] if params == (19,) else []
        else:
            self._one = None
            self._rows = []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._rows)


def test_case_only_taishin_bank_entry_opens_case_without_reconciliation_target(monkeypatch):
    from subsystems.finance_import import query
    monkeypatch.setattr(query, 'resolve_client_virtual_account_suffix',
        lambda _, suffix: {'result':'resolved','case_no':'115000032'} if suffix=='115032' else {'result':'pending'})
    source = {
        'row_id':1,'transaction_date':'2026-11-09','format_id':'taishin','direction':'outgoing',
        'debit':1000,'credit':None,'memo':'ＨＣ１１５０３２服務人員薪資',
        'classification_type':'non_business_review','transaction_status':'pending',
        'disposition':'manual_review','review_reason':'taishin_memo_case_requires_manual_scheme',
        'matched_identity_ids':'[]','target_identities':'[]','bank_references':'{}',
        'counterparty_name':None,'available_actions':'[]','safe_reference':'SYNTHETIC',
    }
    [result] = _enrich_bank_transactions(_EnrichCursor(),[source],{})
    assert result['cases'] == ['115000032']
    assert result['reconciliation_target'] is None
    assert result['reconciliation_unavailable_reason'] == 'purpose_unconfirmed'


@pytest.mark.parametrize('owners,format_id,matched,targets,allowed',[
    ([19],'sinopac',[],[],True),
    ([19],'legacy',[],[],True),
    ([19,20],'sinopac',[],[],False),
    ([],'sinopac',[],[],False),
    ([19],'taishin',[],[],False),
    ([19],'sinopac',[19,20],[],False),
    ([19],'sinopac',[],['staff:19','staff:20'],False),
])
def test_sinopac_legacy_staff_entry_uses_unique_same_case_staff_without_an_account(owners,format_id,matched,targets,allowed):
    import json
    from copy import deepcopy
    class Cursor(_EnrichCursor):
        def __init__(self):super().__init__();self.calls=[]
        def execute(self,statement,params=()):
            self.calls.append((statement,params))
            if 'SELECT DISTINCT staff_id FROM staff_obligations' in statement:
                assert params==('115000001',)
                self._rows=[{'staff_id':identity} for identity in owners]
            elif 'FROM staff_obligations' in statement:
                self._rows=[{'case_no':'115000001','obligation_identity':'legacy:first','amount_due_ntd':12000,'due_date':'2026-10-19','uses_funding_split':0}]
            else:super().execute(statement,params)
    source={
        'row_id':51,'transaction_date':'2026-10-20','format_id':format_id,'direction':'outgoing',
        'debit':11000,'credit':None,'memo':'HC115001','classification_type':'staff_payout',
        'transaction_status':'pending','disposition':'business_pending','review_reason':'sinopac_unique_staff_case_suffix_in_memo',
        'recorded_pending_reason':'staff_bank_account_ambiguous',
        'matched_identity_ids':json.dumps(matched),'target_identities':json.dumps(targets),
        'bank_references':'{}','resolved_counterparty_account':None,'counterparty_name':None,
        'available_actions':'[]','safe_reference':'SYNTHETIC-LEGACY-51',
    }
    original=deepcopy(source);cursor=Cursor()
    [row]=_enrich_bank_transactions(cursor,[source],{})
    assert source==original
    if allowed:
        assert row['reconciliation_target']=={'case_no':'115000001','obligation_identities':['legacy:first'],'staff_id':19}
        assert row['reconciliation_unavailable_reason'] is None
        assert row['review_reason'] == 'staff_payout_amount_mismatch'
    else:assert row['reconciliation_target'] is None
    assert all(statement.startswith('SELECT') for statement,_ in cursor.calls)


@pytest.mark.parametrize("direction,memo,disposition,allowed,reason", [
    ("incoming", "HC115001", "business_pending", True, None),
    ("outgoing", "HC115001", "business_pending", False, "direction_unconfirmed"),
    ("incoming", "無案件參照", "business_pending", False, "case_unconfirmed"),
    ("incoming", "HC115001", "blocked", False, "blocked"),
])
def test_known_case_refund_return_has_original_refund_selection_entry(direction, memo, disposition, allowed, reason):
    [row] = _enrich_bank_transactions(_EnrichCursor(), [{
        "row_id": 31, "transaction_date": "2026-11-02", "format_id": "sinopac",
        "direction": direction, "debit": 12000 if direction == "outgoing" else None,
        "credit": 12000 if direction == "incoming" else None, "memo": memo,
        "classification_type": "client_refund_return", "transaction_status": "pending",
        "review_reason": "sinopac_refund_return_matched",
        "disposition": disposition, "matched_identity_ids": "[]", "target_identities": "[]",
        "bank_references": "{}", "available_actions": "[]", "safe_reference": "RETURN-31",
    }], {})
    if allowed:
        assert row["reconciliation_target"] == {
            "case_no": "115000001", "obligation_identities": [], "staff_id": None,
            "requires_selection": True,
        }
    else:
        assert row["reconciliation_target"] is None
    assert row["reconciliation_unavailable_reason"] == reason


@pytest.mark.parametrize('old_reason,memo,staff_names,direction,format_id,count,allowed',[
    ('subsidy_advance_not_due','HC115001',[],'outgoing','taishin',1,True),
    ('unrecognized_historical_reason','HC115001',[],'outgoing','taishin',1,True),
    (None,'HC115001',[],'outgoing','taishin',1,True),
    ('taishin_client_subsidy_case_suffix_in_memo','HC115001',[],'outgoing','taishin',1,True),
    ('subsidy_advance_not_due','HC115001 HC115001',[],'outgoing','taishin',1,True),
    ('subsidy_advance_not_due','HC115001',[],'outgoing','taishin',2,True),
    ('subsidy_advance_not_due','HC115001',[],'outgoing','taishin',0,True),
    ('taishin_client_subsidy_case_suffix_in_memo','合成月嫂HC115001',['合成月嫂'],'outgoing','taishin',1,False),
    ('subsidy_advance_not_due','HC115001 HC115002',[],'outgoing','taishin',1,False),
    ('subsidy_advance_not_due','HC115999',[],'outgoing','taishin',1,False),
    ('subsidy_advance_not_due','沒有案件六碼',[],'outgoing','taishin',1,False),
    ('taishin_client_subsidy_name_in_memo','合成客戶甲 GB,轉入0000000000000003',[],'outgoing','taishin',1,True),
    ('taishin_client_subsidy_name_in_memo','合成客戶乙 HC115001',[],'outgoing','taishin',1,False),
    ('taishin_client_subsidy_case_suffix_in_memo','HC115001',[],'incoming','taishin',1,False),
    ('subsidy_advance_not_due','HC115001',[],'outgoing','sinopac',1,False),
])
def test_taishin_subsidy_entry_uses_unique_original_memo_instead_of_the_legacy_reason(old_reason,memo,staff_names,direction,format_id,count,allowed):
    from copy import deepcopy
    class Cursor(_EnrichCursor):
        def __init__(self):super().__init__();self.calls=[]
        def execute(self,statement,params=()):
            self.calls.append((statement,params))
            if statement.startswith('SELECT name FROM staff WHERE name IS NOT NULL'):
                self._rows=[{'name':name} for name in staff_names]
            elif statement.startswith('SELECT id,name FROM clients'):
                self._rows = [{'id': 7, 'name': '合成客戶甲'}, {'id': 8, 'name': '合成客戶乙'}]
            elif statement.startswith('SELECT case_no FROM orders WHERE client_id'):
                self._rows = [{'case_no': '115000001'}] if params == (7,) else []
            elif statement.startswith('SELECT client_id FROM orders WHERE case_no'):
                self._rows = [{'client_id': 7}]
            elif statement.startswith('SELECT case_no,due_date,obligation_identity,amount_due_ntd FROM client_obligations'):
                assert params==('115000001',)
                self._rows=[{'case_no':'115000001','obligation_identity':f'subsidy:{i}','amount_due_ntd':12000,'due_date':'2026-10-15'} for i in range(count)]
            else:super().execute(statement,params)
    source={
        'row_id':61,'transaction_date':'2026-10-20','format_id':format_id,'direction':direction,
        'debit':12000 if direction=='outgoing' else None,'credit':12000 if direction=='incoming' else None,
        'memo':memo,'classification_type':'client_subsidy_return','transaction_status':'pending',
        'disposition':'business_pending','review_reason':old_reason,'matched_identity_ids':'[]','target_identities':'[]',
        'bank_references':'{}','counterparty_name':None,'available_actions':'[]','safe_reference':'SYNTHETIC-SUBSIDY-61',
    }
    original=deepcopy(source);cursor=Cursor()
    [row]=_enrich_bank_transactions(cursor,[source],{})
    assert source==original and row['review_reason']==old_reason
    if allowed:
        assert row['reconciliation_target']=={
            'case_no':'115000001','obligation_identities':[f'subsidy:{i}' for i in range(count)],'staff_id':None,
            **({'requires_selection':True} if count!=1 else {}),
        }
    else:assert row['reconciliation_target'] is None
    assert all(statement.startswith('SELECT') for statement,_ in cursor.calls)


@pytest.mark.parametrize('kind,bank,evidence,reason', [
    (FinanceClassificationType.CLIENT_SUBSIDY_RETURN,'taishin','taishin_client_subsidy_case_suffix_in_memo','outgoing_client_refund_multiple_fee_matches'),
    (FinanceClassificationType.CLIENT_REFUND,'sinopac','sinopac_unique_client_refund_account_in_transaction_reference','client_refund_source_account_missing'),
    (FinanceClassificationType.CLIENT_REFUND,'sinopac','sinopac_unique_client_refund_account_in_transaction_reference','due_date_missing'),
    (FinanceClassificationType.STAFF_PAYOUT,'taishin','unique_staff_payout_name_month_fee_matched','due_date_missing'),
    (FinanceClassificationType.STAFF_PAYOUT,'taishin','unique_staff_payout_name_month_fee_matched','staff_memo_recipient_unconfirmed'),
])
def test_refund_matching_reason_survives_apply_receipt_and_query_mapping(monkeypatch,kind,bank,evidence,reason):
    import json
    from dataclasses import replace
    from unittest.mock import Mock
    import subsystems.finance_import.query as query
    from infrastructure.mysql.finance_import_repository import MySqlFinanceImportRepository, _stored_apply_receipt
    from shared_kernel.identities import ActorContext, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.import_workflow import FinanceImportWorkflow, FinanceImportApplyRequest

    row = CanonicalFinanceImportRow('finance-import-row:1', 0, MoneyNTD(12000),
        kind, FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint('a'*64), evidence=(evidence,))
    facts = FinanceImportBatchFacts('finance-import-batch:1', 0, 1, 1, 0, 'b'*64, 'v1', 'v1', (row,))
    repository = Mock(); repository.load.return_value = facts; repository.find_receipt.return_value = None
    port = Mock(); port.resolve.return_value = replace(row, pending_reason=reason)
    unit = Mock(); unit.__enter__ = Mock(return_value=unit); unit.__exit__ = Mock(return_value=False)
    workflow = FinanceImportWorkflow(repository, port, lambda: unit)
    preview = workflow.preview(facts.batch_identity, CorrelationId('synthetic'))
    workflow.apply(FinanceImportApplyRequest(facts.batch_identity, ExpectedVersion(0), preview.fingerprint,
        IdempotencyKey('synthetic-pending'), ActorContext('synthetic'), '合成原因保存', CorrelationId('synthetic')))
    stored = repository.save_receipt.call_args.args[1]
    assert stored.pending_reasons == ((row.row_identity, reason),)
    assert stored.client_receipt_reviews == ()
    port.post.assert_not_called()

    cursor = _Cursor([])
    monkeypatch.setattr(query, 'batch_review_count', lambda *args: 1)
    MySqlFinanceImportRepository(_Connection(cursor)).save_receipt(IdempotencyKey('synthetic-pending'), stored)
    sql, params = cursor.calls[-1]
    payload = json.loads(params[-1])
    assert payload['pending_reasons'] == {row.row_identity: reason}
    assert _stored_apply_receipt({'command_fingerprint':params[1], 'result_snapshot':params[-1]}) == stored

    source = dict(row_id=1, format_id=bank,safe_reference='synthetic',transaction_date='2026-10-20',
        direction='outgoing',debit=12000,credit=0,classification_type=kind.value,transaction_status='pending',
        disposition='business_pending',review_reason=evidence,
        recorded_pending_reason=payload['pending_reasons'][row.row_identity],available_actions='[]',counterparty_name=None)
    assert query._bank_transaction(source, ['C-1'])['recorded_pending_reason'] == reason
    assert query._bank_transaction({**source, 'transaction_status':'posted'}, ['C-1'])['recorded_pending_reason'] is None
    assert query._bank_transaction({**source, 'recorded_pending_reason':None}, ['C-1'])['recorded_pending_reason'] is None


def test_pending_rematch_resolves_across_batches_and_keeps_contested_targets_pending():
    from dataclasses import replace
    from unittest.mock import MagicMock
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.finance_import.import_workflow import (
        FinanceDispatchOutcome, FinanceImportDispatchResult, FinanceImportWorkflow, PendingReconciliationRequest,
    )

    kinds = (
        FinanceClassificationType.STAFF_PAYOUT, FinanceClassificationType.CLIENT_RECEIPT,
        FinanceClassificationType.CLIENT_REFUND, FinanceClassificationType.GOVERNMENT_SUBSIDY,
        FinanceClassificationType.STAFF_PAYOUT,
    )
    rows = tuple(CanonicalFinanceImportRow(
        f"finance-import-row:{number}", 0, MoneyNTD(12000), kind,
        FinanceImportDisposition.BUSINESS_PENDING, PreviewFingerprint("a" * 64),
    ) for number, kind in enumerate(kinds, 1))
    repository = MagicMock()
    repository.load_pending_batches.return_value = tuple(
        (FinanceImportBatchFacts(f"finance-import-batch:{number}", 0, 1, 1, 0, "b" * 64, "v1", "v1", (row,)),
         frozenset({row.row_identity}))
        for number, row in enumerate(rows, 1)
    )
    targets = ("staff-obligation:shared", "client-receipt:unique", "client-refund:unique", None, "staff-obligation:shared")
    posting = MagicMock()
    posting.resolve.side_effect = [
        replace(row, disposition=FinanceImportDisposition.CREATE, target_identities=(target,))
        for row, target in zip(rows, targets, strict=True)
        if target is not None
    ]
    posting.resolve_pending_government.return_value = rows[3]
    posting.post.side_effect = lambda row: FinanceImportDispatchResult(
        row.row_identity, FinanceDispatchOutcome.RECONCILED, "formal-payment",
    )
    unit = MagicMock()
    unit.__enter__.return_value = unit
    receipt = FinanceImportWorkflow(repository, posting, lambda: unit).reconcile_pending(
        PendingReconciliationRequest(IdempotencyKey("rematch:test"), ActorContext("test"), CorrelationId("test")),
    )
    assert (receipt.checked_count, receipt.reconciled_count, receipt.pending_count) == (5, 2, 3)
    assert [call.args[0].row_identity for call in posting.post.call_args_list] == [rows[1].row_identity, rows[2].row_identity]
    unit.commit.assert_called_once()


def test_missing_receipt_due_date_is_saved_as_null_and_decoded_without_inventing_a_date(monkeypatch):
    import json
    from api.schemas.finance_import import FinanceBankClientReceiptReviewView
    from domains.finance_import.planning import ClientReceiptReviewCandidate, ClientReceiptReviewDiagnostic
    from infrastructure.mysql.finance_import_repository import MySqlFinanceImportRepository, _stored_apply_receipt
    from shared_kernel.identities import IdempotencyKey
    from subsystems.finance_import.import_workflow import FinanceImportApplyReceipt, StoredFinanceImportReceipt
    import subsystems.finance_import.query as query
    review=ClientReceiptReviewDiagnostic('due_date_missing',(ClientReceiptReviewCandidate('first','first',None),))
    stored=StoredFinanceImportReceipt(PreviewFingerprint('a'*64),
        FinanceImportApplyReceipt('finance-import-batch:1',1,PreviewFingerprint('b'*64),0,0,1),
        (('finance-import-row:1',review),))
    cursor=_Cursor([])
    monkeypatch.setattr(query,'batch_review_count',lambda *args:1)
    MySqlFinanceImportRepository(_Connection(cursor)).save_receipt(IdempotencyKey('missing-due'),stored)
    _,params=cursor.calls[-1]
    payload=json.loads(params[-1])
    decoded=FinanceBankClientReceiptReviewView.model_validate(payload['client_receipt_reviews']['finance-import-row:1'])
    assert decoded.reason=='due_date_missing'
    assert decoded.candidates[0].due_date is None
    assert _stored_apply_receipt({'command_fingerprint':params[1],'result_snapshot':params[-1]})==stored


def test_enrich_bank_transactions_populates_counterparty_and_cases_for_pending_rows() -> None:
    page = [
        {
            "row_id": 1,
            "transaction_date": "2026-10-15",
            "format_id": "taishin",
            "direction": "incoming",
            "debit": None,
            "credit": Decimal("18000"),
            "sheet_name": "交易明細",
            "source_row": 2,
            "counterparty_name": None,
            "cancellation_code": None,
            "bank_references": '{"sequence":"0001"}',
            "memo": "新竹市政府補助款",
            "matched_identity_ids": "[]",
            "target_identities": "[]",
            "classification_type": "government_subsidy",
            "transaction_status": "pending",
            "disposition": "business_pending",
            "review_reason": "taishin_incoming_government_subsidy",
            "available_actions": "[]",
            "safe_reference": "0001",
        },
        {
            "row_id": 2,
            "transaction_date": "2026-10-15",
            "format_id": "sinopac",
            "direction": "incoming",
            "debit": None,
            "credit": Decimal("6000"),
            "sheet_name": "Sheet1",
            "source_row": 3,
            "counterparty_name": None,
            "cancellation_code": "99781699115001",
            "bank_references": '{"銷帳編號":"99781699115001"}',
            "memo": "轉帳",
            "matched_identity_ids": "[]",
            "target_identities": "[]",
            "classification_type": "client_receipt",
            "transaction_status": "pending",
            "disposition": "business_pending",
            "review_reason": "sinopac_virtual_account_matched",
            "available_actions": "[]",
            "safe_reference": "TX-02",
        },
        {
            "row_id": 3,
            "transaction_date": "2026-10-15",
            "format_id": "taishin",
            "direction": "outgoing",
            "debit": Decimal("12000"),
            "credit": None,
            "sheet_name": "交易明細",
            "source_row": 4,
            "counterparty_name": None,
            "cancellation_code": None,
            "bank_references": '{"sequence":"0003"}',
            "memo": "月嫂薪資",
            "matched_identity_ids": "[19]",
            "target_identities": "[]",
            "classification_type": "staff_salary",
            "transaction_status": "pending",
            "disposition": "business_pending",
            "review_reason": "staff_account_matched",
            "dispatch_reason": "staff_bank_account_ambiguous",
            "available_actions": "[]",
            "safe_reference": "0003",
        },
    ]

    items = _enrich_bank_transactions(_EnrichCursor(), page, {})

    assert [item["review_reason"] for item in items] == [
        "taishin_incoming_government_subsidy",
        "client_receipt_underpaid",
        "staff_account_matched",
    ]
    [cross_month] = _enrich_bank_transactions(
        _EnrichCursor(), [{**page[1], "transaction_date": "2026-11-15"}], {},
    )
    assert cross_month["review_reason"] == "sinopac_client_receipt_month_no_match"
    assert cross_month["reconciliation_target"] == {
        "case_no": "115000001", "obligation_identities": ["receipt:first"], "staff_id": None,
        "requires_selection": True,
    }
    [same_month_exact] = _enrich_bank_transactions(_EnrichCursor([
        {"obligation_identity": "receipt:first", "due_date": "2026-10-19", "amount_due_ntd": 6000},
        {"obligation_identity": "receipt:second", "due_date": "2026-11-19", "amount_due_ntd": 6000},
    ]), [page[1]], {})
    assert same_month_exact["reconciliation_target"] == {
        "case_no": "115000001", "obligation_identities": ["receipt:first"], "staff_id": None,
    }
    [multiple] = _enrich_bank_transactions(_EnrichCursor([
        {"obligation_identity": "receipt:first", "due_date": "2026-10-19", "amount_due_ntd": 6000},
        {"obligation_identity": "receipt:second", "due_date": "2026-10-27", "amount_due_ntd": 6000},
    ]), [page[1]], {})
    assert multiple["reconciliation_target"] == {
        "case_no": "115000001", "obligation_identities": ["receipt:first", "receipt:second"],
        "staff_id": None, "requires_selection": True,
    }

    assert [item["reconciliation_target"] for item in items] == [
        None,
        {"case_no": "115000001", "obligation_identities": ["receipt:first"], "staff_id": None},
        {"case_no": "115000009", "obligation_identities": ["staff:payout"], "staff_id": 19},
    ]
    assert [item["dispatch_reason"] for item in items] == [None, None, "staff_bank_account_ambiguous"]
    [ambiguous] = _enrich_bank_transactions(
        _EnrichCursor(), [{**page[2], "format_id": "sinopac", "memo": "HC115009 HC115010"}], {},
    )
    assert ambiguous["reconciliation_target"] is None
    assert ambiguous["reconciliation_unavailable_reason"] == "case_reference_unconfirmed"
    [unassigned] = _enrich_bank_transactions(_EnrichCursor(), [{**page[2], "matched_identity_ids": "[]"}], {})
    assert unassigned["reconciliation_unavailable_reason"] == "case_unconfirmed"
    [staff_missing] = _enrich_bank_transactions(_EnrichCursor(), [{
        **page[2], "format_id": "sinopac", "memo": "HC115001 月嫂薪資", "matched_identity_ids": "[]",
    }], {})
    assert staff_missing["cases"] == ["115000001"]
    assert staff_missing["reconciliation_target"] is None
    assert staff_missing["reconciliation_unavailable_reason"] == "staff_unconfirmed"
    assert cross_month["reconciliation_unavailable_reason"] == "no_same_month_items"


    assert [(item["counterparty_name"], item["cases"]) for item in items] == [
        ("新竹市政府", []),
        ("林小美", ["115000001"]),
        ("陳月嫂", ["115000009"]),
    ]

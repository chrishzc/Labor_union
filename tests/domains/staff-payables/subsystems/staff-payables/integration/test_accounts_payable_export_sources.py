from dataclasses import replace
from datetime import date
from domains.staff_payables.subsidy_handoff import SubsidyPayableHandoff

import pytest

from infrastructure.mysql.accounts_payable_export_sources import (
    _CLIENT_REFUNDS_SQL,
    _STAFF_PAYABLES_SQL,
    MySqlStaffPayableExportSource,
    _formal_case_audit_item,
    _missing_case_audit_item,
    _refund_fact,
    _staff_fact,
)
from domains.staff_payables.reconciliation import StaffPayableStatus


def _row(*, amount_due=6000, net_refunded=0, obligation_type="subsidy_return"):
    return {
        "obligation_identity": "subsidy:C-1",
        "case_no": "C-1",
        "obligation_type": obligation_type,
        "recipient_name": "客戶",
        "amount_due_ntd": amount_due,
        "due_date": date(2026, 3, 15),
        "refund_bank_code": "004",
        "refund_account_no": "1234567890",
        "net_refunded_ntd": net_refunded,
    }


def test_subsidy_return_is_a_payable_633_fact_when_no_ledger_payout_exists():
    fact = _refund_fact(_row())

    assert fact.refund_type == "subsidy_return"
    assert fact.payable is True
    assert fact.anomaly is False


@pytest.mark.parametrize('scheme,portion,bank,payable', [
    ('split', 'subsidy', '633', True), ('split', 'client', '31', True),
    ('split', None, '31', False), ('unknown', 'subsidy', '31', False),
    ('waiting', 'subsidy', '31', False), ('advance', 'subsidy', '31', True),
    ('direct', None, '31', True),
])
def test_formal_scheme_is_required_before_a_funding_portion_routes_to_taishin(scheme, portion, bank, payable):
    from infrastructure.mysql.accounts_payable_export_sources import _staff_payment_route
    case = SubsidyPayableHandoff(scheme, False, True, 12000, False)
    row = {**_partially_paid_staff_row(), 'installment_funding': portion, 'union_no': '0007'}
    fact = _staff_fact(_staff_payment_route(row, case))
    assert fact.outgoing_bank == bank
    assert fact.staff_union_no == '0007'
    assert (fact.status is StaffPayableStatus.PARTIALLY_PAID) is payable


def test_full_subsidy_routes_existing_staff_balance_without_creating_a_second_entitlement():
    from infrastructure.mysql.accounts_payable_export_sources import _staff_payment_route
    case = SubsidyPayableHandoff('split', False, True, 12000, True)
    fact = _staff_fact(_staff_payment_route(_partially_paid_staff_row(), case))
    assert fact.outgoing_bank == '633' and fact.amount.amount == 1500


def test_reopened_refund_is_payable_again_after_a_refund_return_reversal():
    fact = _refund_fact(_row(obligation_type="refund", amount_due=300, net_refunded=0))

    assert fact.refund_type == "customer_refund"
    assert fact.payable is True


def test_sql_nets_every_canonical_client_refund_reversal_type():
    for entry_type in (
        "reversal",
        "refund_reversal",
        "subsidy_return_reversal",
        "subsidy_advance_reversal",
    ):
        assert "'" + entry_type + "'" in _CLIENT_REFUNDS_SQL
    assert "obligations.obligation_type" in _CLIENT_REFUNDS_SQL


def test_staff_payables_only_include_the_selected_payment_date():
    assert "obligations.due_date = %s" in _STAFF_PAYABLES_SQL
    assert "obligations.due_date <= %s" not in _STAFF_PAYABLES_SQL

    for query in (_CLIENT_REFUNDS_SQL,):
        assert "due_date <= %s" in query

    assert "obligations.status = 'open'" in _CLIENT_REFUNDS_SQL


def test_historical_confirmation_excludes_only_the_exact_obligation_amount_and_version():
    assert "historical_confirmation.amount_snapshot_ntd = obligations.amount_due_ntd" in _STAFF_PAYABLES_SQL
    assert "historical_confirmation.obligation_payroll_version = obligations.payroll_version" in _STAFF_PAYABLES_SQL
    assert "historical_confirmation.obligation_identity IS NULL" in _STAFF_PAYABLES_SQL


def test_case_audit_keeps_exact_historical_settlement_visible_without_relisting_it():
    item = _formal_case_audit_item(
        {
            "obligation_identity": "service:C-1:assignment:7",
            "case_no": "C-1",
            "staff_id": 7,
            "recipient_name": "月嫂甲",
            "amount_due_ntd": 42_000,
            "export_amount_ntd": 42_000,
            "due_date": date(2026, 10, 15),
            "order_due_date": date(2026, 10, 15),
            "payout_status": "payable",
            "historical_confirmation_kind": "settled",
            "primary_account_count": 0,
            "bank_code": None,
            "account_no": None,
        },
        date(2026, 10, 15),
    )

    assert item.disposition == "paid_or_settled"
    assert item.balance.amount == 0
    assert item.payment_status == "settled"
    assert item.effective_due_date == date(2026, 10, 15)


def test_case_audit_reports_unknown_amount_and_unformed_date_instead_of_zero():
    item = _missing_case_audit_item(
        {
            "case_no": "C-MISSING",
            "staff_payment_due_date": None,
            "staff_id": None,
            "recipient_name": None,
        }
    )

    assert item.amount_due is None
    assert item.balance is None
    assert item.disposition == "date_not_formed"


class _CanonicalCursor:
    def __init__(self, formal_rows=(), order_status="訂單完成"):
        self.formal_rows = formal_rows
        self.order_status = order_status
        self.rows = ()
        self.statements = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, statement, parameters):
        self.statements.append((statement, parameters))
        if "historical_confirmation.confirmation_kind AS" in statement:
            self.rows = self.formal_rows
        elif "SELECT orders.case_no,orders.staff_payment_due_date" in statement:
            self.rows = ({"case_no": "C-1", "staff_payment_due_date": date(2026, 3, 15), "status": self.order_status},)
        elif "FROM scheduling_aggregates" in statement:
            self.rows = ()
        elif "FROM case_staff_assignments assignment" in statement:
            self.rows = ({"id": 91, "staff_id": 1}, {"id": 92, "staff_id": 2})
        elif "SELECT id,name FROM staff" in statement:
            self.rows = ({"id": 1, "name": "月嫂甲"}, {"id": 2, "name": "月嫂乙"})
        else:
            self.rows = ()
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class _CanonicalConnection:
    def __init__(self, formal_rows=(), order_status="訂單完成"):
        self.cursor_instance = _CanonicalCursor(formal_rows, order_status)
    def cursor(self): return self.cursor_instance


def test_missing_obligation_is_not_recalculated_by_export_query():
    connection = _CanonicalConnection()
    source = MySqlStaffPayableExportSource(connection)
    assert source.load(date(2026, 3, 15)) == ()
    assert len(connection.cursor_instance.statements) == 1
    items = source.load_case("C-1", date(2026, 3, 15))
    assert [item.staff_id for item in items] == [1, 2]
    assert all(item.source == "order_facts" for item in items)
    assert all(item.amount_due is None and item.balance is None for item in items)
    assert all("尚未建立月嫂應付帳務" in item.reason for item in items)


@pytest.mark.parametrize(("outcome", "reason"), [
    ({"action": "skipped", "reason": "historical_payroll_attribution_pending", "detail": "待核對原付款證據。"},
     "待核對原付款證據。"),
    ({"action": "created", "due_date": "2026-03-15", "amount_ntd": 12000},
     "已查到同步所需資料，可同步月嫂應付。本次查核尚未入帳。"),
    ({"action": "created", "due_date": None, "amount_ntd": 48000,
      "detail": "月嫂付款來源與補助流向尚未確認。"},
     "已查到同步所需資料，可同步月嫂應付。本次查核尚未入帳。月嫂付款來源與補助流向尚未確認。"),
])
def test_historical_case_audit_uses_current_payroll_preview_without_reporting_payment_as_created(
    monkeypatch, outcome, reason
):
    paid = _partially_paid_staff_row(payout_status="completed", export_amount_ntd=0)
    connection = _CanonicalConnection((paid,), order_status="歷史訂單－服務完成")

    def preview(conn, case_no, *, dry_run):
        assert (conn, case_no, dry_run) == (connection, "C-1", True)
        return outcome

    monkeypatch.setattr("subsystems.payroll.historical_baseline_obligation_sync.synchronize_historical_payroll", preview)
    item_paid, item_missing = MySqlStaffPayableExportSource(connection).load_case("C-1", date(2026, 3, 15))

    assert item_paid.disposition == "paid_or_settled"
    assert item_missing.reason == reason
    assert item_missing.source == "order_facts"
    assert item_missing.amount_due is None and item_missing.effective_due_date is None


@pytest.mark.parametrize(("order_status", "payroll_reason", "reason", "preview_count"), [
    ("歷史訂單－服務完成", "historical_payroll_attribution_pending", "待核對原付款證據。", 1),
    ("歷史訂單－服務完成", "historical_payroll_funding_conflict", "列入所選付款月份。", 1),
    ("訂單完成", "historical_payroll_attribution_pending", "列入所選付款月份。", 0),
])
def test_case_audit_surfaces_pending_historical_attribution_without_changing_formal_payables(
    monkeypatch, order_status, payroll_reason, reason, preview_count,
):
    due_date = date(2026, 3, 15)
    unpaid = _partially_paid_staff_row()
    settled = _partially_paid_staff_row(staff_id=2, obligation_identity="staff:2", historical_confirmation_kind="settled")
    connection = _CanonicalConnection((unpaid, settled), order_status=order_status)
    calls = []

    def preview(conn, case_no, *, dry_run):
        calls.append((conn, case_no, dry_run))
        return {"action": "skipped", "reason": payroll_reason, "detail": "待核對原付款證據。"}

    monkeypatch.setattr("subsystems.payroll.historical_baseline_obligation_sync.synchronize_historical_payroll", preview)
    item_unpaid, item_settled = MySqlStaffPayableExportSource(connection).load_case("C-1", due_date)

    assert calls == [(connection, "C-1", True)] * preview_count
    assert item_unpaid == replace(_formal_case_audit_item(unpaid, due_date), reason=reason)
    assert item_settled == _formal_case_audit_item(settled, due_date)


def test_current_assignment_and_paid_obligation_are_composed_once_without_relisting_paid_staff():
    row = _partially_paid_staff_row(payout_status="completed", export_amount_ntd=0)
    connection = _CanonicalConnection((row,))
    items = MySqlStaffPayableExportSource(connection).load_case("C-1", date(2026, 3, 15))
    assert [(item.staff_id, item.payment_status) for item in items] == [(1, "paid"), (2, "pending")]
    assert items[0].balance.amount == 0
    assert items[1].amount_due is None and items[1].source == "order_facts"
    assert sum("FROM case_staff_assignments assignment" in sql for sql, _ in connection.cursor_instance.statements) == 1


def _partially_paid_staff_row(**overrides):
    return {
            "obligation_identity": "staff:1",
            "case_no": "C-1",
            "staff_id": 1,
            "recipient_name": "月嫂",
            "identity_card": "A123456789",
            "amount_due_ntd": 20000,
            "export_amount_ntd": 1500,
            "due_date": date(2026, 3, 15),
            "payout_status": "partially_paid",
            "primary_account_count": 1,
            "bank_code": "012",
            "account_no": "1234567890",
            **overrides,
        }


def test_partially_paid_staff_exports_only_the_remaining_balance():
    fact = _staff_fact(_partially_paid_staff_row())

    assert fact.status is StaffPayableStatus.PARTIALLY_PAID
    assert fact.amount.amount == 1500
    assert "IN ('payable', 'partially_paid')" in _STAFF_PAYABLES_SQL
    assert "COALESCE(projection.balance_ntd, obligations.amount_due_ntd) > 0" in _STAFF_PAYABLES_SQL


def test_partially_paid_case_audit_preserves_original_amount_and_current_balance():
    row = _partially_paid_staff_row(order_due_date=date(2026, 3, 15))
    item = _formal_case_audit_item(row, date(2026, 3, 15))
    assert item.disposition == "selected_month"
    assert item.amount_due.amount == 20_000
    assert item.balance.amount == 1500
    assert item.payment_status == "partially_paid"

    other_month = _formal_case_audit_item(row, date(2026, 4, 15))
    assert other_month.disposition == "other_month"

    undated = _formal_case_audit_item({**row, "due_date": None}, date(2026, 3, 15))
    assert undated.disposition == "date_not_formed"


@pytest.mark.parametrize("overrides", [
    {"primary_account_count": 0},
    {"primary_account_count": 2},
    {"recipient_name": ""},
    {"bank_code": ""},
    {"account_no": ""},
    {"payout_status": "anomaly"},
    {"payout_status": "recovery_required"},
])
def test_partial_payment_does_not_bypass_other_payment_blockers(overrides):
    row = _partially_paid_staff_row(**overrides)
    fact = _staff_fact(row)
    assert fact.status not in {StaffPayableStatus.PAYABLE, StaffPayableStatus.PARTIALLY_PAID}
    assert _formal_case_audit_item(row, date(2026, 3, 15)).disposition == "blocked"


class _RecipientSnapshotCursor:
    def __init__(self, sources, existing=False):
        self.sources, self.existing = sources, existing
        self.rows = ()
        self.inserts = []
        self.rowcount = 0

    def execute(self, sql, params):
        if sql.startswith('SELECT refund_obligation_identity'):
            self.rows = ({'refund_obligation_identity': params[0]},) if self.existing else ()
        elif sql.startswith('SELECT br.refund_bank_code,br.refund_account_no,cs.effective_values_json '):
            self.rows = self.sources
        elif sql.startswith('INSERT INTO client_refund_recipient_snapshots'):
            self.inserts.append(params)
            self.existing = True
            self.rowcount = 1
        else:
            raise AssertionError('unexpected statement')

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_customer_refund_snapshot_uses_unique_bound_source_and_never_overwrites_on_replay():
    from infrastructure.mysql.client_receipt_reconciliation_repository import _insert_refund_recipient_snapshot
    # Synthetic numeric account satisfies the existing normalization contract.
    cursor = _RecipientSnapshotCursor(({'refund_bank_code':'0040000','refund_account_no':'000001'},))
    assert _insert_refund_recipient_snapshot(cursor,'refund:1','CASE-1','subsidy_return') is True
    cursor.sources = ({'refund_bank_code':'9999999','refund_account_no':'different-account'},)
    assert _insert_refund_recipient_snapshot(cursor,'refund:1','CASE-1','subsidy_return') is False
    assert len(cursor.inserts) == 1
    assert cursor.inserts[0] == ('refund:1','CASE-1','0040000','000001','subsidy_return')


@pytest.mark.parametrize('sources', [(), ({'refund_bank_code':'0040000','refund_account_no':None},),
    ({'refund_bank_code':'0040000','refund_account_no':'one'}, {'refund_bank_code':'0040000','refund_account_no':'two'})])
def test_missing_or_ambiguous_customer_account_stays_pending_without_inventing_a_snapshot(sources):
    from infrastructure.mysql.client_receipt_reconciliation_repository import _insert_refund_recipient_snapshot
    cursor = _RecipientSnapshotCursor(sources)
    assert _insert_refund_recipient_snapshot(cursor,'refund:1','CASE-1','subsidy_return',require_complete=False) is False
    assert cursor.inserts == []
    with pytest.raises(ValueError,match='client_refund_recipient_snapshot_missing'):
        _insert_refund_recipient_snapshot(cursor,'refund:1','CASE-1','receipt_overage')
    assert cursor.inserts == []

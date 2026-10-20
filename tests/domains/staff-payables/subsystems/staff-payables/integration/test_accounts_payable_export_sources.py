from datetime import date

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
    def __init__(self, formal_rows=()):
        self.formal_rows = formal_rows
        self.rows = ()
        self.statements = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, statement, parameters):
        self.statements.append((statement, parameters))
        if "historical_confirmation.confirmation_kind AS" in statement:
            self.rows = self.formal_rows
        elif "SELECT orders.case_no,orders.staff_payment_due_date" in statement:
            self.rows = ({"case_no": "C-1", "staff_payment_due_date": date(2026, 3, 15)},)
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
    def __init__(self, formal_rows=()): self.cursor_instance = _CanonicalCursor(formal_rows)
    def cursor(self): return self.cursor_instance


def test_missing_historical_obligation_is_not_recalculated_by_export_query():
    connection = _CanonicalConnection()
    source = MySqlStaffPayableExportSource(connection)
    assert source.load(date(2026, 3, 15)) == ()
    assert len(connection.cursor_instance.statements) == 1
    items = source.load_case("C-1", date(2026, 3, 15))
    assert [item.staff_id for item in items] == [1, 2]
    assert all(item.source == "order_facts" for item in items)
    assert all(item.amount_due is None and item.balance is None for item in items)
    assert all("尚未建立月嫂應付帳務" in item.reason for item in items)


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

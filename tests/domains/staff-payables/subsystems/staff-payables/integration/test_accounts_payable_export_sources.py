from datetime import date

from infrastructure.mysql.accounts_payable_export_sources import (
    _CLIENT_REFUNDS_SQL,
    _GOVERNMENT_RETURNS_SQL,
    _HISTORICAL_STAFF_PAYABLE_PROJECTION_SQL,
    _STAFF_PAYABLES_SQL,
    MySqlStaffPayableExportSource,
    _formal_case_audit_item,
    _government_return_fact,
    _historical_case_audit_item,
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

    for query in (_CLIENT_REFUNDS_SQL, _GOVERNMENT_RETURNS_SQL):
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


class _ProjectionCursor:
    def __init__(self, historical_rows):
        self.historical_rows = historical_rows
        self.rows = ()
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statements.append((statement, parameters))
        self.rows = self.historical_rows if statement == _HISTORICAL_STAFF_PAYABLE_PROJECTION_SQL else ()

    def fetchall(self):
        return self.rows


class _ProjectionConnection:
    def __init__(self, historical_rows):
        self.cursor_instance = _ProjectionCursor(historical_rows)

    def cursor(self):
        return self.cursor_instance


def test_existing_historical_order_without_obligation_is_projected_on_each_load():
    row = {
        "case_no": "H-19",
        "assignment_id": 19,
        "staff_id": 3,
        "recipient_name": "月嫂甲",
        "identity_card": "A123456789",
        "contracted_service_days": 40,
        "service_hours_per_day": 9,
        "floor_fee_ntd": 4_000,
        "actual_service_days": 26,
        "payroll_policy_version": "payroll-rate:citizen:v1",
        "payroll_policy_kind": "citizen",
        "payroll_hourly_rate_ntd": 300,
        "adjustment_amount_ntd": 0,
        "identity_status": "一般市民",
        "client_policy_version": "client-rate:citizen:v1",
        "client_hourly_rate_ntd": 300,
        "completed_on": date(2026, 4, 20),
        "staff_payment_due_date": None,
        "primary_account_count": 1,
        "bank_code": "012",
        "account_no": "1234567890",
    }
    connection = _ProjectionConnection((row,))

    facts = MySqlStaffPayableExportSource(connection).load(date(2026, 5, 15))

    assert len(facts) == 1
    assert facts[0].obligation_identity == (
        "historical-service:H-19:revision:1:assignment:19:payable_to_staff"
    )
    assert facts[0].amount.amount == 72_800
    assert facts[0].payment_date == date(2026, 5, 15)
    assert "NOT EXISTS" in _HISTORICAL_STAFF_PAYABLE_PROJECTION_SQL

    row["actual_service_days"] = 20
    refreshed = MySqlStaffPayableExportSource(connection).load(date(2026, 5, 15))

    assert refreshed[0].amount.amount == 56_000

    later_month = MySqlStaffPayableExportSource(connection).load(date(2026, 9, 15))

    assert later_month == ()

    row["adjustment_amount_ntd"] = -100_000
    blocked = _historical_case_audit_item(row, date(2026, 5, 15))

    assert blocked.disposition == "blocked"
    assert blocked.amount_due is None
    assert blocked.balance is None


def test_historical_projection_does_not_include_a_future_due_date():
    row = {
        "case_no": "H-20",
        "assignment_id": 20,
        "staff_id": 4,
        "recipient_name": "月嫂乙",
        "identity_card": "B123456789",
        "contracted_service_days": 40,
        "service_hours_per_day": 9,
        "floor_fee_ntd": 0,
        "actual_service_days": 10,
        "payroll_policy_version": "payroll-rate:subsidized-citizen:v1",
        "payroll_policy_kind": "subsidized_citizen",
        "payroll_hourly_rate_ntd": 350,
        "adjustment_amount_ntd": 0,
        "identity_status": "補助市民",
        "client_policy_version": "client-rate:subsidized-citizen:v1",
        "client_hourly_rate_ntd": 350,
        "completed_on": date(2026, 4, 20),
        "staff_payment_due_date": None,
        "primary_account_count": 1,
        "bank_code": "012",
        "account_no": "1234567890",
    }
    connection = _ProjectionConnection((row,))

    facts = MySqlStaffPayableExportSource(connection).load(date(2026, 5, 15))

    assert facts == ()


def test_legacy_partially_paid_staff_row_is_an_anomaly_not_a_current_export():
    fact = _staff_fact(
        {
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
        }
    )

    assert fact.status is StaffPayableStatus.ANOMALY
    assert "'partially_paid'" not in _STAFF_PAYABLES_SQL
    assert "= 'payable'" in _STAFF_PAYABLES_SQL


def test_government_return_is_a_next_payment_detail_without_payment_reconciliation():
    fact = _government_return_fact({
        "payable_identity": "government-return:1",
        "overpayment_identity": "overpayment:1",
        "agency_name": "新竹市政府",
        "bank_code": "004",
        "account_display": "****1234",
        "remaining_amount_ntd": 500,
        "due_date": date(2026, 3, 15),
    })

    assert fact.amount.amount == 500
    assert fact.overpayment_identity == "overpayment:1"
    assert "finance_import_rows" not in _GOVERNMENT_RETURNS_SQL

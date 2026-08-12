from datetime import date

from infrastructure.mysql.accounts_payable_export_sources import (
    _CLIENT_REFUNDS_SQL,
    _GOVERNMENT_RETURNS_SQL,
    _government_return_fact,
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


def test_partially_paid_staff_export_uses_only_its_remaining_balance():
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

    assert fact.status is StaffPayableStatus.PARTIALLY_PAID
    assert fact.amount.amount == 1500


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

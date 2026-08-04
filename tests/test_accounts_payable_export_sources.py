from datetime import date

from infrastructure.mysql.accounts_payable_export_sources import (
    _CLIENT_REFUNDS_SQL,
    _refund_fact,
)


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


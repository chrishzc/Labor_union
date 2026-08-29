from domains.client_finance.client_refund_reversal import (
    ClientRefundBankFact,
    ClientRefundObligation,
    build_client_refund_candidate,
    build_client_refund_overage_candidate,
)
from shared_kernel.money import MoneyNTD


def test_normal_refund_does_not_accept_a_bank_payment_larger_than_the_payable() -> None:
    try:
        build_client_refund_candidate(_CASE_NO, _bank_facts(750), _obligations(500))
    except ValueError as error:
        assert str(error) == "allocation_exceeds_obligation"
    else:
        raise AssertionError("normal refund must not absorb an overpayment")


def test_refund_overage_preserves_full_outgoing_cash_and_creates_recovery_balance() -> None:
    candidate = build_client_refund_overage_candidate(_CASE_NO, _bank_facts(750), _obligations(500))

    assert candidate.correction_type.value == "refund_overage"
    assert candidate.amount == MoneyNTD(750)
    assert sum(item.amount.amount for item in candidate.allocations) == 500
    assert candidate.recovery_amount == MoneyNTD(250)


_CASE_NO = "case-1"


def _bank_facts(amount: int) -> tuple[ClientRefundBankFact, ...]:
    return (ClientRefundBankFact("row-1", _CASE_NO, MoneyNTD(amount), "2026-08-05"),)


def _obligations(amount: int) -> tuple[ClientRefundObligation, ...]:
    return (ClientRefundObligation("refund:case-1", _CASE_NO, MoneyNTD(amount), "refund"),)

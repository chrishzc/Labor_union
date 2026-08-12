from domains.client_finance.reconciliation import (
    ClientObligation,
    IncomingBankFact,
    PaymentStage,
    ReconciliationStatus,
    build_reconciliation_candidate,
)
from shared_kernel.money import MoneyNTD


def test_client_receipt_overage_is_blocked_by_the_normal_action() -> None:
    candidate = build_reconciliation_candidate(_bank_facts(3000), _obligations(2500))

    assert candidate.status is ReconciliationStatus.REVIEW_REQUIRED
    assert candidate.blockers == ("client_receipt_overpaid",)
    assert candidate.allocations == ()


def test_client_receipt_overage_disposition_preserves_cash_and_creates_refund_amount() -> None:
    candidate = build_reconciliation_candidate(
        _bank_facts(3000),
        _obligations(2500),
        allow_overage_disposition=True,
    )

    assert candidate.status is ReconciliationStatus.OVERAGE
    assert candidate.bank_total == MoneyNTD(3000)
    assert sum(item.amount.amount for item in candidate.allocations) == 2500
    assert candidate.overage_amount == MoneyNTD(500)
    assert candidate.blockers == ("client_receipt_overpaid",)


def _bank_facts(amount: int) -> tuple[IncomingBankFact, ...]:
    return (IncomingBankFact("row-1", MoneyNTD(amount), PaymentStage.DEPOSIT),)


def _obligations(amount: int) -> tuple[ClientObligation, ...]:
    return (
        ClientObligation(
            "case-1:deposit",
            "case-1",
            MoneyNTD(amount),
            PaymentStage.DEPOSIT,
        ),
    )

from datetime import date

import pytest

from domains.client_finance.subsidy_advance import (
    SubsidyAdvanceDecisionKind,
    SubsidyAdvanceFacts,
    build_subsidy_advance_decision,
    build_subsidy_advance_recovery,
)
from shared_kernel.money import MoneyNTD


def _facts(receipt_amount=0):
    return SubsidyAdvanceFacts(
        "CASE-001",
        date(2026, 1, 31),
        MoneyNTD(6000),
        MoneyNTD(receipt_amount),
    )


def test_first_quarter_month_advance_is_due_on_second_following_month_15th():
    decision = build_subsidy_advance_decision(_facts(), date(2026, 3, 15))

    assert decision.refund_due_on == date(2026, 3, 15)
    assert decision.kind is SubsidyAdvanceDecisionKind.READY
    assert decision.payout_amount == MoneyNTD(6000)


def test_second_quarter_month_never_qualifies_for_this_advance_policy():
    facts = SubsidyAdvanceFacts("CASE-002", date(2026, 2, 1), MoneyNTD(6000), MoneyNTD(0))

    decision = build_subsidy_advance_decision(facts, date(2026, 4, 15))

    assert decision.kind is SubsidyAdvanceDecisionKind.NOT_FIRST_QUARTER_MONTH


def test_advance_is_not_available_before_the_fixed_refund_date():
    decision = build_subsidy_advance_decision(_facts(), date(2026, 3, 14))

    assert decision.kind is SubsidyAdvanceDecisionKind.NOT_DUE
    assert decision.payout_amount is None


def test_advance_requires_an_open_positive_subsidy_return_obligation():
    with pytest.raises(ValueError, match="subsidy return due must be positive"):
        SubsidyAdvanceFacts("CASE-001", date(2026, 1, 31), MoneyNTD(0), MoneyNTD(0))


def test_matching_government_receipt_prevents_union_advance():
    decision = build_subsidy_advance_decision(_facts(6000), date(2026, 3, 15))

    assert decision.kind is SubsidyAdvanceDecisionKind.GOVERNMENT_RECEIPT_ALLOCATED


def test_partial_government_receipt_requires_human_review():
    decision = build_subsidy_advance_decision(_facts(5000), date(2026, 3, 15))

    assert decision.kind is SubsidyAdvanceDecisionKind.REVIEW_REQUIRED


def test_recovery_requires_exact_government_allocation_for_the_advance():
    recovery = build_subsidy_advance_recovery(
        _facts(6000),
        "client-ledger-12",
        "government-allocation-42",
        MoneyNTD(6000),
        MoneyNTD(0),
    )

    assert recovery.amount == MoneyNTD(6000)


def test_recovery_rejects_mismatched_or_previously_recovered_amounts():
    with pytest.raises(ValueError, match="subsidy_advance_settlement_ambiguous"):
        build_subsidy_advance_recovery(
            _facts(5000), "client-ledger-12", "government-allocation-42", MoneyNTD(6000), MoneyNTD(0)
        )

    with pytest.raises(ValueError, match="subsidy_advance_already_recovered"):
        build_subsidy_advance_recovery(
            _facts(6000), "client-ledger-12", "government-allocation-42", MoneyNTD(6000), MoneyNTD(1)
        )

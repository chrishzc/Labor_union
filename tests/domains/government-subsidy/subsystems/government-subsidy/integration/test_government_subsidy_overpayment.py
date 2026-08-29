from domains.government_subsidy.overpayment import (
    GovernmentRecipientSnapshot, GovernmentSubsidyOffsetIntent,
    GovernmentSubsidyOffsetTarget, GovernmentSubsidyOverpayment,
    GovernmentSubsidyOverpaymentError, GovernmentSubsidyOverpaymentStatus,
    build_overpayment_offset_candidate, build_overpayment_return_candidate,
    build_receipt_with_overage_candidate, build_overpayment_return_reconciliation_candidate,
)
from domains.government_subsidy.ledger import (
    ClaimBatchFacts, ClaimBatchIdentity, ClaimItemSnapshot,
    GovernmentBankFact, GovernmentSubsidyBankDirection,
)
from datetime import date
from shared_kernel.money import MoneyNTD


def test_offset_consumes_credit_without_creating_a_new_bank_receipt() -> None:
    candidate = build_overpayment_offset_candidate(
        _overpayment(),
        (_target(9, 1200),),
        (GovernmentSubsidyOffsetIntent(9, MoneyNTD(1200)),),
    )
    assert candidate.disposition_kind == "offset"
    assert candidate.remaining_after_ntd == MoneyNTD(800)
    assert candidate.resulting_status is GovernmentSubsidyOverpaymentStatus.OFFSET_RESERVED


def test_fully_offset_root_is_a_valid_closed_projection() -> None:
    root = GovernmentSubsidyOverpayment(
        "over-closed", "city-a", MoneyNTD(0),
        GovernmentSubsidyOverpaymentStatus.OFFSET_APPLIED, 2,
    )
    assert root.remaining_amount_ntd == MoneyNTD(0)


def test_offset_rejects_different_government_payer() -> None:
    try:
        build_overpayment_offset_candidate(
            _overpayment(), (_target(9, 1200, payer="city-b"),),
            (GovernmentSubsidyOffsetIntent(9, MoneyNTD(1200)),),
        )
    except GovernmentSubsidyOverpaymentError as error:
        assert str(error) == "government_subsidy_overpayment_cross_payer"
    else:
        raise AssertionError("cross-payer offset must be rejected")


def test_offset_preview_fingerprint_binds_target_batch_version() -> None:
    intent = (GovernmentSubsidyOffsetIntent(9, MoneyNTD(1200)),)
    initial = build_overpayment_offset_candidate(_overpayment(), (_target(9, 1200),), intent)
    changed_target = GovernmentSubsidyOffsetTarget(
        9, 1, 5, MoneyNTD(2000), MoneyNTD(800), "city-a",
        MoneyNTD(1200), True, True,
    )
    changed = build_overpayment_offset_candidate(
        _overpayment(), (changed_target,), intent
    )
    assert initial.fingerprint != changed.fingerprint


def test_return_is_exclusive_with_offset_disposition() -> None:
    candidate = build_overpayment_return_candidate(_overpayment(), _recipient())
    assert candidate.resulting_status is GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE
    try:
        build_overpayment_offset_candidate(
            GovernmentSubsidyOverpayment("over-1", "city-a", MoneyNTD(2000), GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE, 1),
            (_target(9, 1200),), (GovernmentSubsidyOffsetIntent(9, MoneyNTD(1200)),),
        )
    except GovernmentSubsidyOverpaymentError as error:
        assert str(error) == "government_subsidy_overpayment_disposition_conflict"
    else:
        raise AssertionError("return payable may not also be offset")


def test_return_creates_a_full_payable_without_an_outgoing_bank_fact() -> None:
    candidate = build_overpayment_return_candidate(_overpayment(), _recipient())

    assert candidate.disposition_amount_ntd == MoneyNTD(2000)
    assert candidate.remaining_after_ntd == MoneyNTD(2000)
    assert candidate.resulting_status is GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE


def test_return_reconciliation_uses_the_canonical_outgoing_bank_fact_not_due_date() -> None:
    root = GovernmentSubsidyOverpayment(
        "over-1", "city-a", MoneyNTD(2000),
        GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE, 2,
    )
    early_bank_fact = GovernmentBankFact(
        10, "bank-out-10", GovernmentSubsidyBankDirection.OUTGOING,
        "government_subsidy", MoneyNTD(2000), date(2026, 7, 1),
    )

    candidate = build_overpayment_return_reconciliation_candidate(
        root, "return-1", MoneyNTD(2000), 1, early_bank_fact
    )

    assert candidate.remaining_after_ntd == MoneyNTD(0)
    assert candidate.resulting_status is GovernmentSubsidyOverpaymentStatus.RETURNED


def test_receipt_with_overage_keeps_only_approved_amount_in_claim_allocation() -> None:
    candidate = build_receipt_with_overage_candidate(
        GovernmentBankFact(8, "bank-8", GovernmentSubsidyBankDirection.INCOMING, "government_subsidy", MoneyNTD(1200), date(2026, 8, 1)),
        _batch(), (GovernmentSubsidyOffsetIntent(7, MoneyNTD(1000)),),
    )
    assert candidate.allocated_amount_ntd == MoneyNTD(1000)
    assert candidate.overpayment_amount_ntd == MoneyNTD(200)
    assert candidate.resulting_outstanding_ntd == MoneyNTD(0)


def _overpayment():
    return GovernmentSubsidyOverpayment("over-1", "city-a", MoneyNTD(2000), GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW, 0)


def _target(item_id, amount, payer="city-a"):
    return GovernmentSubsidyOffsetTarget(
        item_id, 1, 4, MoneyNTD(2000), MoneyNTD(800), payer,
        MoneyNTD(amount), True, True,
    )


def _recipient():
    return GovernmentRecipientSnapshot("city-a", "City A", "004", "****1234", "f" * 64, "2026-08-01", "2026-09-05", "notice-1")


def _batch():
    item = ClaimItemSnapshot(7, 1, 3, "case-1", 4, 10, MoneyNTD(100), MoneyNTD(1000), MoneyNTD(1000), MoneyNTD(0))
    return ClaimBatchFacts(1, ClaimBatchIdentity(2026, 3, 1), 2, True, True, (item,))

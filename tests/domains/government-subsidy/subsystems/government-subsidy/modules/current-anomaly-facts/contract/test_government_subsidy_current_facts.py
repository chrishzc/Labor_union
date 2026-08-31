from subsystems.government_subsidy.current_anomaly_facts import (
    GovernmentSubsidyAllocationCurrentFact,
    GovernmentSubsidyCurrentFactReason,
    GovernmentSubsidyReceiptCurrentFact,
    GovernmentSubsidyReversalCurrentFact,
)


def test_receipt_requires_unique_batch_complete_allocation_and_conservation() -> None:
    fact = GovernmentSubsidyReceiptCurrentFact(
        "bank-1", "snapshot-1", 3, True, False, False, False
    )
    assert fact.unresolved_reason_codes == (
        GovernmentSubsidyCurrentFactReason.APPROVED_BATCH_NOT_UNIQUE,
        GovernmentSubsidyCurrentFactReason.RECEIPT_ALLOCATION_INCOMPLETE,
        GovernmentSubsidyCurrentFactReason.AMOUNT_NOT_CONSERVED,
    )


def test_manual_allocation_completion_is_closed_and_incomplete_readback_fails_closed() -> None:
    complete = GovernmentSubsidyAllocationCurrentFact(
        "bank-1", 5, "snapshot-2", 4, True, True, True, True
    )
    incomplete = GovernmentSubsidyAllocationCurrentFact(
        "bank-1", 5, "snapshot-3", 4, False, True, True, True
    )
    assert complete.predicate_active is False
    assert incomplete.unresolved_reason_codes == (
        GovernmentSubsidyCurrentFactReason.OWNER_READBACK_INCOMPLETE,
    )


def test_reversal_requires_exact_valid_target_and_complete_amount() -> None:
    fact = GovernmentSubsidyReversalCurrentFact(
        "bank-out-1", 91, "snapshot-4", 8, True, True, True, False, False
    )
    assert fact.unresolved_reason_codes == (
        GovernmentSubsidyCurrentFactReason.REVERSAL_AMOUNT_EXCEEDED,
        GovernmentSubsidyCurrentFactReason.REVERSAL_ALLOCATION_INCOMPLETE,
    )

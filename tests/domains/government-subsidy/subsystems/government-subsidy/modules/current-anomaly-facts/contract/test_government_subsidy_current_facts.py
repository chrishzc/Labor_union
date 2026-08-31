from types import SimpleNamespace

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.government_subsidy.current_anomaly_facts import (
    GovernmentSubsidyAllocationCurrentFact,
    GovernmentSubsidyCurrentFactReason,
    GovernmentSubsidyReceiptCurrentFact,
    GovernmentSubsidyReversalCurrentFact,
    build_government_subsidy_recheck_requests,
)


def test_receipt_requires_unique_batch_complete_allocation_and_conservation() -> None:
    fact = GovernmentSubsidyReceiptCurrentFact(
        "bank-1", 11, "snapshot-1", 3, True, False, False, False
    )
    assert fact.unresolved_reason_codes == (
        GovernmentSubsidyCurrentFactReason.APPROVED_BATCH_NOT_UNIQUE,
        GovernmentSubsidyCurrentFactReason.RECEIPT_ALLOCATION_INCOMPLETE,
        GovernmentSubsidyCurrentFactReason.AMOUNT_NOT_CONSERVED,
    )


def test_manual_allocation_completion_is_closed_and_incomplete_readback_fails_closed() -> None:
    complete = GovernmentSubsidyAllocationCurrentFact(
        "bank-1", 5, 11, "snapshot-2", 4, True, True, True, True
    )
    incomplete = GovernmentSubsidyAllocationCurrentFact(
        "bank-1", 5, None, "snapshot-3", 4, False, True, True, True
    )
    assert complete.predicate_active is False
    assert incomplete.unresolved_reason_codes == (
        GovernmentSubsidyCurrentFactReason.OWNER_READBACK_INCOMPLETE,
    )


def test_reversal_requires_exact_valid_target_and_complete_amount() -> None:
    fact = GovernmentSubsidyReversalCurrentFact(
        "bank-out-1", 91, 12, "snapshot-4", 8, True, True, True, False, False
    )
    assert fact.unresolved_reason_codes == (
        GovernmentSubsidyCurrentFactReason.REVERSAL_AMOUNT_EXCEEDED,
        GovernmentSubsidyCurrentFactReason.REVERSAL_ALLOCATION_INCOMPLETE,
    )


def test_reversal_apply_receipt_builds_exact_govsub004_recheck() -> None:
    fingerprint = fingerprint_payload({"reversal": "bank-out-1"})
    request = SimpleNamespace(intent=SimpleNamespace(source_receipt_id=91))
    receipt = SimpleNamespace(
        kind=SimpleNamespace(value="reversal"),
        bank_fact_identity="bank-out-1",
        batch_id=5,
        batch_version=8,
        preview_fingerprint=fingerprint,
    )

    rechecks = build_government_subsidy_recheck_requests(
        request,
        receipt,
        "government-subsidy:reversal-1",
    )

    assert len(rechecks) == 1
    assert rechecks[0].definition_code.value == "GOVSUB-004"
    assert rechecks[0].subject_ids == ("bank-out-1:91",)
    assert rechecks[0].owner_root_ids == (
        "bank:bank-out-1",
        "batch:5",
        "receipt:91",
    )

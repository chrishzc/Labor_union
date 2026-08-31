from subsystems.case_import.pairing_current_facts import (
    BeClassCounterpartCurrentFact,
    CasePairingAcceptedLineage,
    CasePairingCurrentFactReason,
    HcmCounterpartCurrentFact,
)


def test_hcm_missing_and_ambiguous_counterparts_remain_active() -> None:
    missing = HcmCounterpartCurrentFact("CASE-1", "snapshot-1", 1, True, 0, False)
    ambiguous = HcmCounterpartCurrentFact("CASE-1", "snapshot-2", 2, True, 2, False)
    assert missing.unresolved_reason_codes == (CasePairingCurrentFactReason.COUNTERPART_MISSING,)
    assert ambiguous.unresolved_reason_codes == (CasePairingCurrentFactReason.COUNTERPART_AMBIGUOUS,)


def test_exact_accepted_mapping_closes_pairing_predicate() -> None:
    fact = BeClassCounterpartCurrentFact(
        "client_counterpart", "counterpart:source-1", "snapshot-3", 3, True, 1, True
    )
    assert fact.predicate_active is False


def test_incomplete_readback_is_fail_closed() -> None:
    fact = BeClassCounterpartCurrentFact(
        "client", "beclass-review:abc", "snapshot-4", 0, False, 0, False
    )
    assert fact.unresolved_reason_codes[0] is CasePairingCurrentFactReason.OWNER_READBACK_INCOMPLETE


def test_lineage_keeps_review_source_and_acceptance_result_separate() -> None:
    lineage = CasePairingAcceptedLineage(
        "beclass-review:original",
        "beclass-workbook:" + "c" * 64 + ":row:8",
        "client-beclass-apply-event:result-8",
    )
    assert lineage.original_review_identity != lineage.accepted_source_event_identity
    assert lineage.accepted_source_event_identity != lineage.accepted_result_identity

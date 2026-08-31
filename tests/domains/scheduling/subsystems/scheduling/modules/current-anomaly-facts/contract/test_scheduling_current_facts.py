from subsystems.scheduling.current_anomaly_facts import (
    SchedulingCoverageCurrentFact,
    SchedulingCurrentFactReason,
    SchedulingOverlapCurrentFact,
    SchedulingReplacementCurrentFact,
    build_scheduling_recheck_request,
)


def test_replacement_requires_every_owner_completion_fact() -> None:
    fact = SchedulingReplacementCurrentFact(7, "snapshot-7", 3, True, True, False, True, False, True)
    assert fact.predicate_active is True
    assert fact.unresolved_reason_codes == (
        SchedulingCurrentFactReason.DAILY_OUTCOME_INCOMPLETE,
        SchedulingCurrentFactReason.PAYROLL_IMPACT_INCOMPLETE,
    )


def test_overlap_identity_and_recheck_scope_are_canonical() -> None:
    fact = SchedulingOverlapCurrentFact(7, 9, "snapshot-overlap", 4, True, True)
    request = build_scheduling_recheck_request(fact, "schedule-overlap:7:9:4")
    assert request.subject_ids == ("7:9",)
    assert request.owner_root_ids == ("assignment:7", "assignment:9")


def test_coverage_closed_reasons_do_not_collapse_to_day_count() -> None:
    fact = SchedulingCoverageCurrentFact("CASE-1", 2, "snapshot-coverage", 8, True, True, True, True, False, False, True)
    assert fact.unresolved_reason_codes == (
        SchedulingCurrentFactReason.HOURS_MISMATCH,
        SchedulingCurrentFactReason.STAFF_OCCUPANCY_CONFLICT,
    )


def test_incomplete_readback_is_always_active() -> None:
    fact = SchedulingOverlapCurrentFact(1, 2, "snapshot-incomplete", 1, False, False)
    assert fact.unresolved_reason_codes == (SchedulingCurrentFactReason.OWNER_READBACK_INCOMPLETE,)

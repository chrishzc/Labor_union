from datetime import date

from domains.orders.historical_precision_restart import (
    HistoricalPrecisionRestartAssignmentFacts,
    HistoricalPrecisionRestartFacts,
    HistoricalPrecisionRestartIntent,
    build_historical_precision_restart_candidate,
)
from domains.orders.lifecycle import OrderLifecycleStatus


def _facts(status=OrderLifecycleStatus.HISTORICAL_UNSERVED, *, revision=0, open_obligations=0, payroll_obligations=0):
    return HistoricalPrecisionRestartFacts(
        "CASE-1", status, 3, 4, 2, 5, 6, revision,
        date(2026, 5, 19),
        date(2026, 5, 19) if status is OrderLifecycleStatus.HISTORICAL_IN_SERVICE else None,
        3, 8, False,
        (HistoricalPrecisionRestartAssignmentFacts("assignment:7", 7, 3, "王月嫂", 1),),
        current_assignment_ids=(7,),
        open_nonstage_obligation_count=open_obligations,
        adoption_receipt_id=17,
        adoption_source_identity="historical-source:17",
        payroll_obligation_count=payroll_obligations,
    )


def _candidate(facts):
    return build_historical_precision_restart_candidate(
        facts, HistoricalPrecisionRestartIntent("CASE-1")
    )


def test_unserved_restart_returns_to_established_with_empty_scheduling_tombstone():
    candidate = _candidate(_facts())

    assert candidate.blockers == ()
    assert candidate.target_status is OrderLifecycleStatus.ESTABLISHED
    assert candidate.actual_end_date is None
    assert candidate.scheduling is not None
    assert candidate.scheduling.cancelled_assignment_ids == (7,)
    assert candidate.scheduling.assignments == ()
    assert candidate.scheduling.buffers == ()
    assert candidate.scheduling.resulting_aggregate_version == 5


def test_in_service_restart_also_returns_to_established_without_reusing_source_dates():
    candidate = _candidate(_facts(OrderLifecycleStatus.HISTORICAL_IN_SERVICE))

    assert candidate.blockers == ()
    assert candidate.target_status is OrderLifecycleStatus.ESTABLISHED
    assert candidate.actual_end_date is None
    assert candidate.scheduling is not None
    assert candidate.scheduling.assignments == ()


def test_completed_and_accounting_completed_are_not_eligible():
    for status in (
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    ):
        assert _candidate(_facts(status)).blockers == (
            "historical_precision_restart_not_eligible",
        )


def test_existing_historical_accounting_or_open_obligation_fails_closed():
    assert _candidate(_facts(revision=1)).blockers == (
        "historical_precision_restart_accounting_bridge_required",
    )
    assert _candidate(_facts(open_obligations=1)).blockers == (
        "historical_precision_restart_accounting_bridge_required",
    )
    assert _candidate(_facts(payroll_obligations=1)).blockers == (
        "historical_precision_restart_accounting_bridge_required",
    )


def test_case_identity_mismatch_fails_closed():
    candidate = build_historical_precision_restart_candidate(
        _facts(), HistoricalPrecisionRestartIntent("OTHER")
    )

    assert candidate.blockers == (
        "historical_precision_restart_assignment_mismatch",
    )

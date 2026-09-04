"""
File: test_order_actual_start_workflow.py
Description: 驗證實際開工 command 契約及非 AutoComplete workflow 的 lifecycle 邊界。
"""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pymysql.err import IntegrityError

from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.fingerprints import PreviewFingerprint
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus, _lifecycle_status
from domains.orders.actual_start import (
    ActualStartBlocker,
    ActualStartCandidateError,
    ActualStartAssignmentFacts,
    ActualStartOrderFacts,
    ActualStartSchedulingFacts,
    build_actual_start_candidate,
)
from domains.orders.terms import ServiceTimeTerms
from subsystems.orders.actual_start_workflow import ActualStartApplyRequest
from infrastructure.mysql.order_actual_start_repository import (
    _is_effective_staff_date_conflict,
)


def _request(*, reason: str = "confirm service start") -> ActualStartApplyRequest:
    return ActualStartApplyRequest(
        "CASE-1",
        date(2026, 8, 3),
        ExpectedVersion(1),
        ExpectedVersion(2),
        ExpectedVersion(3),
        ExpectedVersion(4),
        PreviewFingerprint("a" * 64),
        IdempotencyKey("actual-start-1"),
        ActorContext("admin"),
        reason,
        CorrelationId("actual-start-correlation"),
    )


def test_actual_start_request_uses_direct_canonical_source_contract() -> None:
    request = _request()

    assert request.case_no == "CASE-1"
    assert request.new_actual_start_date == date(2026, 8, 3)


def test_actual_start_request_rejects_blank_change_reason() -> None:
    with pytest.raises(ValueError, match="change reason"):
        _request(reason=" ")


def test_actual_start_lifecycle_impact_cannot_bypass_auto_completion_owner() -> None:
    roots = OrderLifecycleRootFacts(
        case_no="CASE-1",
        current_status=OrderLifecycleStatus.ESTABLISHED,
        contract_completed=True,
        actual_start_date=date(2026, 8, 20),
        actual_start_reconfirmed=True,
        cancellation_effective=False,
        service_data_locked=False,
    )
    settlement = SimpleNamespace(deposit_settled=True)

    status = _lifecycle_status(
        roots,
        settlement,
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 24, 18, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    assert status is OrderLifecycleStatus.IN_SERVICE


def test_actual_start_maps_effective_staff_date_duplicate_to_typed_conflict() -> None:
    error = IntegrityError(
        1062,
        "Duplicate entry '531-2026-08-20-1' for key "
        "'staff_schedule.uq_staff_schedule_effective_date'",
    )

    assert _is_effective_staff_date_conflict(error) is True
    assert _is_effective_staff_date_conflict(
        IntegrityError(
            1062,
            "Duplicate entry '531-2026-08-11' for key "
            "'scheduling_effective_occupancy.PRIMARY'",
        )
    ) is True
    assert _is_effective_staff_date_conflict(IntegrityError(1062, "other")) is False


def test_actual_start_can_replace_legacy_dates_with_recalculated_official_dates() -> None:
    order = ActualStartOrderFacts(
        "CASE-1",
        3,
        None,
        False,
        ServiceTimeTerms(None, None, None),
    )
    scheduling = ActualStartSchedulingFacts(
        "CASE-1",
        5,
        1,
        date(2026, 8, 1),
        (
            ActualStartAssignmentFacts(
                11,
                22,
                1,
                date(2026, 8, 1),
                date(2026, 8, 3),
                (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)),
            ),
        ),
    )

    candidate = build_actual_start_candidate(
        order,
        scheduling,
        date(2026, 8, 8),
        8,
        (date(2026, 8, 8), date(2026, 8, 11), date(2026, 8, 12)),
    )

    assert candidate.official_service_dates == (
        date(2026, 8, 8),
        date(2026, 8, 11),
        date(2026, 8, 12),
    )
    assert candidate.actual_end_date == date(2026, 8, 12)


def test_actual_start_keeps_current_service_data_lock_blocker() -> None:
    order = ActualStartOrderFacts(
        "CASE-LOCKED", 3, None, True, ServiceTimeTerms(None, None, None)
    )
    scheduling = ActualStartSchedulingFacts(
        "CASE-LOCKED",
        5,
        1,
        date(2026, 8, 1),
        (
            ActualStartAssignmentFacts(
                11, 22, 1, date(2026, 8, 1), date(2026, 8, 1),
                (date(2026, 8, 1),),
            ),
        ),
    )

    with pytest.raises(ActualStartCandidateError) as error:
        build_actual_start_candidate(order, scheduling, date(2026, 8, 2), 8)

    assert error.value.blocker is ActualStartBlocker.SERVICE_DATA_LOCKED


def test_normal_actual_start_still_requires_canonical_scheduling_assignment() -> None:
    order = ActualStartOrderFacts(
        "CASE-NORMAL", 3, None, False, ServiceTimeTerms(None, None, None)
    )
    scheduling = ActualStartSchedulingFacts(
        "CASE-NORMAL", 5, 1, date(2026, 8, 1), ()
    )

    with pytest.raises(ActualStartCandidateError) as error:
        build_actual_start_candidate(order, scheduling, date(2026, 8, 2), 8)

    assert error.value.blocker is ActualStartBlocker.SCHEDULING_ASSIGNMENTS_REQUIRED

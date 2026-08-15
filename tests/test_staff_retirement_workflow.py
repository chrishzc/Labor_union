"""
File: test_staff_retirement_workflow.py
Description: 驗證人員退役 lifecycle 的純規則、no-op 與冪等重播。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domains.staff.retirement import (
    StaffLifecycleFact,
    StaffLifecycleState,
    StaffLifecycleTransition,
    build_transition,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.clock import FixedBusinessClock
from subsystems.staff.retirement_workflow import (
    StaffLifecycleApplyRequest,
    StaffLifecycleWorkflow,
)


class _UnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self) -> None:
        self.committed = True


class _Repository:
    def __init__(self, fact: StaffLifecycleFact) -> None:
        self.fact = fact
        self.receipts = {}
        self.persist_calls = 0

    def load(self, staff_id: int, *, lock: bool) -> StaffLifecycleFact:
        assert staff_id == self.fact.staff_id
        return self.fact

    def claim_command(self, request, command_fingerprint) -> None:
        existing = self.receipts.get(request.idempotency_key.value)
        if existing is not None and existing[0] != command_fingerprint:
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key: IdempotencyKey):
        return self.receipts.get(key.value)

    def persist(self, request, preview, receipt, command_fingerprint) -> None:
        self.persist_calls += 1
        if not preview.candidate.is_noop:
            self.fact = preview.candidate.after
        self.receipts[request.idempotency_key.value] = (command_fingerprint, receipt)


def _request(workflow, *, transition, version, key="staff-retirement-1"):
    effective_at = datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc)
    preview = workflow.preview(7, transition, effective_at, _reason(transition))
    return StaffLifecycleApplyRequest(
        7,
        transition,
        effective_at,
        _reason(transition),
        ExpectedVersion(version),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("admin-1"),
        CorrelationId("staff-retirement-correlation-1"),
    )


def _reason(transition: StaffLifecycleTransition) -> str:
    return "left_union" if transition is StaffLifecycleTransition.RETIRE else "returned_to_service"


def test_retiring_active_staff_advances_state_and_version() -> None:
    candidate = build_transition(
        StaffLifecycleFact(7, StaffLifecycleState.ACTIVE, 2),
        StaffLifecycleTransition.RETIRE,
        effective_at=datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc),
        reason_code="left_union",
    )

    assert candidate.after == StaffLifecycleFact(7, StaffLifecycleState.RETIRED, 3, datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc), "left_union")
    assert candidate.is_noop is False


def test_retiring_already_retired_staff_is_version_preserving_noop() -> None:
    candidate = build_transition(
        StaffLifecycleFact(7, StaffLifecycleState.RETIRED, 3),
        StaffLifecycleTransition.RETIRE,
        effective_at=datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc),
        reason_code="left_union",
    )

    assert candidate.after == StaffLifecycleFact(7, StaffLifecycleState.RETIRED, 3)
    assert candidate.is_noop is True


def test_apply_replays_same_idempotency_key_without_second_persist() -> None:
    repository = _Repository(StaffLifecycleFact(7, StaffLifecycleState.ACTIVE, 0))
    unit_of_work = _UnitOfWork()
    workflow = StaffLifecycleWorkflow(repository, lambda: unit_of_work, FixedBusinessClock(datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)))
    request = _request(workflow, transition=StaffLifecycleTransition.RETIRE, version=0)

    first = workflow.apply(request)
    second = workflow.apply(request)

    assert first == second
    assert repository.persist_calls == 1
    assert repository.fact == StaffLifecycleFact(
        7,
        StaffLifecycleState.RETIRED,
        1,
        datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc),
        "left_union",
    )
    assert unit_of_work.committed is True


def test_apply_noop_persists_receipt_without_advancing_state() -> None:
    repository = _Repository(StaffLifecycleFact(7, StaffLifecycleState.RETIRED, 4))
    workflow = StaffLifecycleWorkflow(repository, _UnitOfWork, FixedBusinessClock(datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)))

    receipt = workflow.apply(_request(workflow, transition=StaffLifecycleTransition.RETIRE, version=4))

    assert receipt.version == 4
    assert repository.persist_calls == 1
    assert repository.fact == StaffLifecycleFact(7, StaffLifecycleState.RETIRED, 4)


def test_preview_rejects_future_effective_time_and_invalid_reason() -> None:
    now = datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)
    workflow = StaffLifecycleWorkflow(
        _Repository(StaffLifecycleFact(7, StaffLifecycleState.ACTIVE, 0)),
        _UnitOfWork,
        FixedBusinessClock(now),
    )

    with pytest.raises(ValueError, match="future_effective"):
        workflow.preview(7, StaffLifecycleTransition.RETIRE, now + timedelta(microseconds=1), "left_union")
    with pytest.raises(ValueError, match="reason_invalid"):
        workflow.preview(7, StaffLifecycleTransition.RETIRE, now, "other")

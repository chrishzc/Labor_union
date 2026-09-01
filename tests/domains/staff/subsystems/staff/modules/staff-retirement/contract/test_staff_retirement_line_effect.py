"""Staff retirement to LINE staff-role revocation contract tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from api.routes.staff_retirement import _raise_line_effect_error
from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from domains.staff.retirement import StaffLifecycleFact, StaffLifecycleState, StaffLifecycleTransition
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.identity_management_application import request_staff_retirement_revocation
from subsystems.line.identity_management_contracts import (
    LineIdentityRevocationRequest,
    LineIdentityRevocationStatus,
)
from subsystems.staff.retirement_workflow import StaffLifecycleApplyRequest, StaffLifecycleWorkflow


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


class _AppendOnly:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


class _LineIdentities:
    def __init__(self):
        self.current = LineIdentityBindingSnapshot(
            LineUserId("U-retired-staff"),
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(3),
            LineBindingSubjectType.STAFF,
            "7",
        )
        self.requested_subject_type = None

    def get_by_subject(self, subject_type, subject_reference):
        assert (subject_type, subject_reference) == (LineBindingSubjectType.STAFF, "7")
        return self.current

    def get(self, line_user_id, subject_type=None):
        assert line_user_id == self.current.line_user_id
        assert subject_type is LineBindingSubjectType.STAFF
        return self.current

    def request_revocation(self, *arguments):
        self.requested_subject_type = arguments[-1]
        return LineIdentityBindingSnapshot(
            self.current.line_user_id,
            LineIdentityBindingStatus.REVOCATION_PENDING,
            ExpectedVersion(4),
            self.current.subject_type,
            self.current.subject_reference,
        )


class _IdentityManagement:
    def __init__(self):
        self.command = None

    def get_request_by_key(self, _key):
        return None

    def default_menu_publication(self):
        return {"id": 91, "line_rich_menu_id": "richmenu-default"}

    def create_request(self, command, pending, publication):
        self.command = command
        return LineIdentityRevocationRequest(
            70,
            pending.line_user_id,
            pending.subject_type,
            pending.subject_reference,
            LineIdentityRevocationStatus.PENDING_MENU_RESET,
            command.expected_version,
            pending.version,
            publication["id"],
            publication["line_rich_menu_id"],
            command.actor.actor_id,
            command.reason,
            command.idempotency_key.value,
            command.correlation_id.value,
            0,
            None,
            None,
        )


class _LineUnitOfWork:
    def __init__(self):
        self.identities = _LineIdentities()
        self.identity_management = _IdentityManagement()
        self.outbox = _AppendOnly()
        self.audit = _AppendOnly()


def test_retirement_requests_exact_staff_role_revocation_in_given_uow() -> None:
    unit_of_work = _LineUnitOfWork()

    requested = request_staff_retirement_revocation(
        unit_of_work,
        staff_id=7,
        lifecycle_version=4,
        correlation_id=CorrelationId("staff-retirement-7-v4"),
    )

    assert requested is True
    assert unit_of_work.identities.requested_subject_type is LineBindingSubjectType.STAFF
    assert unit_of_work.identity_management.command.idempotency_key == IdempotencyKey(
        "staff-retirement-line-revoke:7:4"
    )
    assert len(unit_of_work.outbox.items) == 1
    assert len(unit_of_work.audit.items) == 1


class _LifecycleRepository:
    def __init__(self):
        self.fact = StaffLifecycleFact(7, StaffLifecycleState.ACTIVE, 0)
        self.receipt = None

    def load(self, _staff_id, *, lock):
        return self.fact

    def claim_command(self, _request, _fingerprint):
        return None

    def load_receipt(self, _key):
        return self.receipt

    def persist(self, _request, preview, receipt, fingerprint):
        self.fact = preview.candidate.after
        self.receipt = (fingerprint, receipt)


class _OpenAssignmentRepository(_LifecycleRepository):
    def ensure_no_open_assignments(self, _staff_id, *, lock):
        assert lock is False
        raise ValueError("staff_retirement_open_assignments")


class _Effect:
    def __init__(self):
        self.unit_of_work = None

    def on_transition(self, unit_of_work, _request, _preview, _receipt):
        self.unit_of_work = unit_of_work


class _LifecycleUnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


def test_staff_transition_and_line_effect_share_one_outer_uow() -> None:
    repository = _LifecycleRepository()
    effect = _Effect()
    unit_of_work = _LifecycleUnitOfWork()
    workflow = StaffLifecycleWorkflow(
        repository,
        lambda: unit_of_work,
        FixedBusinessClock(NOW),
        effect,
    )
    effective_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    preview = workflow.preview(7, StaffLifecycleTransition.RETIRE, effective_at, "left_union")
    request = StaffLifecycleApplyRequest(
        7,
        StaffLifecycleTransition.RETIRE,
        effective_at,
        "left_union",
        ExpectedVersion(0),
        preview.fingerprint,
        IdempotencyKey("staff-retirement-7-v1"),
        ActorContext("admin:7"),
        CorrelationId("staff-retirement-7-v1"),
    )

    workflow.apply(request)

    assert effect.unit_of_work is unit_of_work
    assert unit_of_work.committed is True


def test_retirement_preview_fails_closed_when_staff_has_open_assignment() -> None:
    repository = _OpenAssignmentRepository()
    workflow = StaffLifecycleWorkflow(
        repository,
        lambda: _LifecycleUnitOfWork(),
        FixedBusinessClock(NOW),
    )

    try:
        workflow.preview(
            7,
            StaffLifecycleTransition.RETIRE,
            datetime(2026, 8, 30, tzinfo=timezone.utc),
            "left_union",
        )
    except ValueError as error:
        assert str(error) == "staff_retirement_open_assignments"
    else:
        raise AssertionError("retirement preview must reject open assignments")


@pytest.mark.parametrize(
    ("error_code", "status_code", "category"),
    [
        ("line_identity_binding_not_found", 404, "not_found"),
        ("line_identity_default_menu_not_published", 409, "domain_blocked"),
        ("line_identity_staff_retirement_revocation_blocked", 409, "domain_blocked"),
        ("line_identity_revocation_idempotency_conflict", 409, "idempotency_mismatch"),
    ],
)
def test_known_line_effect_failures_are_typed_and_not_internal(
    error_code: str, status_code: int, category: str,
) -> None:
    with pytest.raises(HTTPException) as captured:
        _raise_line_effect_error(RuntimeError(error_code), CorrelationId("staff-line-error"))

    assert captured.value.status_code == status_code
    assert captured.value.detail["error"]["code"] == error_code
    assert captured.value.detail["error"]["category"] == category

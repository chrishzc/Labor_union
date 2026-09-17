"""Verify assigned-caregiver notification recipients use canonical bound staff identities."""

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from infrastructure.mysql import line_notification_repository as repository_module
from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from shared_kernel.identities import ExpectedVersion


def _binding(status: LineIdentityBindingStatus) -> LineIdentityBindingSnapshot:
    return LineIdentityBindingSnapshot(
        LineUserId("U-caregiver-4"),
        status,
        ExpectedVersion(3),
        LineBindingSubjectType.STAFF,
        "4",
    )


def test_assigned_caregiver_resolves_bound_staff_identity(monkeypatch) -> None:
    lookups = []

    class _IdentityRepository:
        def __init__(self, connection):
            assert connection is connection_marker

        def get_by_subject(self, subject_type, subject_reference):
            lookups.append((subject_type, subject_reference))
            return _binding(LineIdentityBindingStatus.BOUND)

    connection_marker = object()
    monkeypatch.setattr(
        repository_module,
        "MySqlLineIdentityRepository",
        _IdentityRepository,
    )

    recipient = MySqlLineNotificationRepository(connection_marker)._resolve_recipient(
        "assigned_caregiver",
        {"staff_id": 4},
        source_domain="scheduling",
    )

    assert lookups == [(LineBindingSubjectType.STAFF, "4")]
    assert recipient is not None
    assert recipient.recipient_type.value == "user"
    assert recipient.identity == LineUserId("U-caregiver-4")


def test_assigned_caregiver_rejects_pending_review_identity(monkeypatch) -> None:
    class _IdentityRepository:
        def __init__(self, _connection):
            pass

        def get_by_subject(self, subject_type, subject_reference):
            assert subject_type is LineBindingSubjectType.STAFF
            assert subject_reference == "4"
            return _binding(LineIdentityBindingStatus.PENDING_REVIEW)

    monkeypatch.setattr(
        repository_module,
        "MySqlLineIdentityRepository",
        _IdentityRepository,
    )

    recipient = MySqlLineNotificationRepository(object())._resolve_recipient(
        "assigned_caregiver",
        {"staff_id": 4},
        source_domain="scheduling",
    )

    assert recipient is None

"""Contract tests for the single role-scoped LINE identity application surface."""

from __future__ import annotations

from datetime import datetime, timezone

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.identity_management_application import (
    LineIdentityManagementApplication,
)
from subsystems.line.identity_management_contracts import (
    LineIdentityRoleContextStatus,
    SelectLineIdentityRoleCommand,
)
from subsystems.line.rich_menu_binding import schedule_revocation_successor_menu


class _Identities:
    def __init__(self, line_user_id: LineUserId) -> None:
        self.bindings = (
            LineIdentityBindingSnapshot(
                line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(1),
                LineBindingSubjectType.CUSTOMER,
                "customer:7",
            ),
            LineIdentityBindingSnapshot(
                line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(1),
                LineBindingSubjectType.STAFF,
                "staff:8",
            ),
        )
        self.selected = None
        self.context_version = ExpectedVersion(0)

    def list_by_user(self, line_user_id):
        assert line_user_id == self.bindings[0].line_user_id
        return self.bindings

    def selected_role(self, line_user_id):
        assert line_user_id == self.bindings[0].line_user_id
        return self.selected, self.context_version

    def select_role(self, line_user_id, subject_type, expected_version):
        assert expected_version == self.context_version
        self.selected = subject_type
        self.context_version = ExpectedVersion(expected_version.value + 1)
        return self.context_version


class _AppendOnly:
    def __init__(self) -> None:
        self.items = []

    def append(self, item) -> None:
        self.items.append(item)


class _Receipts(_AppendOnly):
    def get(self, key):
        return next((item for item in self.items if item.key == key), None)


class _UnitOfWork:
    def __init__(self, identities) -> None:
        self.identities = identities
        self.receipts = _Receipts()
        self.audit = _AppendOnly()
        self.outbox = _AppendOnly()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.commits += 1


def test_customer_and_staff_share_one_context_and_one_selected_role_state() -> None:
    line_user_id = LineUserId("U-role-context")
    unit_of_work = _UnitOfWork(_Identities(line_user_id))
    application = LineIdentityManagementApplication(
        lambda: unit_of_work,
        lambda: datetime(2026, 8, 30, tzinfo=timezone.utc),
    )

    before = application.role_context(line_user_id)
    assert before.available_roles == (
        LineBindingSubjectType.CUSTOMER,
        LineBindingSubjectType.STAFF,
    )
    assert before.status is LineIdentityRoleContextStatus.SELECTION_REQUIRED
    assert before.effective_role is None

    preview = application.preview_role_selection(
        line_user_id,
        LineBindingSubjectType.STAFF,
    )
    command = SelectLineIdentityRoleCommand(
        line_user_id,
        LineBindingSubjectType.STAFF,
        preview.readback.context_version,
        preview.preview_fingerprint,
        ActorContext("staff:operator"),
        IdempotencyKey("select-role:u-role-context:staff"),
        CorrelationId("select-role:u-role-context"),
    )
    receipt = application.select_role(command)

    assert receipt.replayed is False
    assert receipt.readback.status is LineIdentityRoleContextStatus.SELECTED
    assert receipt.readback.effective_role is LineBindingSubjectType.STAFF
    assert len(unit_of_work.outbox.items) == 1
    assert unit_of_work.outbox.items[0].idempotency_identity == (
        "rich-menu-bind:U-role-context:staff:1"
    )

    replay = application.select_role(command)
    assert replay.replayed is True
    assert replay.receipt_identity == receipt.receipt_identity
    assert len(unit_of_work.outbox.items) == 1


def test_staff_revocation_queues_a_distinct_customer_successor_menu() -> None:
    line_user_id = LineUserId("U-role-context")
    identities = _Identities(line_user_id)
    identities.bindings = (identities.bindings[0],)
    unit_of_work = _UnitOfWork(identities)

    assert schedule_revocation_successor_menu(unit_of_work, line_user_id, 70) is True
    assert unit_of_work.outbox.items[0].idempotency_identity == (
        "rich-menu-bind:U-role-context:customer:1:revocation:70"
    )

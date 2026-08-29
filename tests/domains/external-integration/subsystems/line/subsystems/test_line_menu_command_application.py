import json
from types import SimpleNamespace

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import ExpectedVersion
from subsystems.line.menu_command_application import LineMenuCommandApplication


class _Outbox:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


class _Audit:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


def _inbox(event_id="event-1"):
    return SimpleNamespace(event=SimpleNamespace(event_id=SimpleNamespace(value=event_id)))


def _uow(binding=None):
    return SimpleNamespace(
        identities=SimpleNamespace(get=lambda _line_user_id: binding),
        outbox=_Outbox(),
        audit=_Audit(),
    )


def test_union_menu_requires_a_bound_admin_identity():
    binding = LineIdentityBindingSnapshot(
        LineUserId("U-admin"), LineIdentityBindingStatus.BOUND, ExpectedVersion(2),
        LineBindingSubjectType.ADMIN, "admin-7",
    )
    unit_of_work = _uow(binding)

    assert LineMenuCommandApplication().handle(_inbox(), unit_of_work, LineUserId("U-admin"), "工會選單") is True
    assert json.loads(unit_of_work.outbox.items[0].payload_json)["menu_definition_id"] == "union_staff_menu"
    assert unit_of_work.outbox.items[0].idempotency_identity == "line-menu-command:union-menu:event-1"


def test_union_menu_rejects_a_non_admin_and_esc_resets_every_user_to_default_menu():
    binding = LineIdentityBindingSnapshot(
        LineUserId("U-customer"), LineIdentityBindingStatus.BOUND, ExpectedVersion(2),
        LineBindingSubjectType.CUSTOMER, "client-7",
    )
    unit_of_work = _uow(binding)
    application = LineMenuCommandApplication()

    assert application.handle(_inbox(), unit_of_work, LineUserId("U-customer"), "工會選單") is False
    assert application.handle(_inbox("event-2"), unit_of_work, LineUserId("U-customer"), "esc") is True
    assert json.loads(unit_of_work.outbox.items[0].payload_json)["menu_definition_id"] == "default_menu"
    assert unit_of_work.outbox.items[0].idempotency_identity == "line-menu-command:esc:event-2"

"""Subsystem coverage for durable identity-to-Rich-Menu binding."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from domains.line.identities import LineRichMenuPublicationId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import ExpectedVersion
from subsystems.line.outbox_contracts import LineOutboxWorkItem
from subsystems.line.rich_menu_binding import (
    LineRichMenuBindingWorker,
    RICH_MENU_BINDING_INTENT,
    schedule_rich_menu_binding,
)
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
)
from subsystems.line.rich_menu_worker import LineRichMenuWorker

NOW = datetime(2026, 8, 11, 4, tzinfo=timezone.utc)


class RecordingOutbox:
    def __init__(self, claimed=()) -> None:
        self.appended = []
        self.claimed = tuple(claimed)
        self.completed = []

    def append(self, intent) -> None:
        self.appended.append(intent)

    def claim(self, query):
        assert query.intent_type == RICH_MENU_BINDING_INTENT
        result, self.claimed = self.claimed, ()
        return result

    def complete(self, command) -> None:
        self.completed.append(command)


class FakeUow:
    def __init__(
        self,
        outbox,
        provider_menu_id="richmenu-staff",
        identities=None,
    ) -> None:
        self.outbox = outbox
        self.rich_menu_publications = PublishedMenus(provider_menu_id)
        self.identities = identities or BoundIdentities(())
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self) -> None:
        self.committed = True


class PublishedMenus:
    def __init__(self, provider_menu_id) -> None:
        self.provider_menu_id = provider_menu_id

    def published_provider_menu_id(self, menu_definition_id):
        assert menu_definition_id == "staff_menu"
        return self.provider_menu_id

    def record(self, command):
        self.recorded = command


class BoundIdentities:
    def __init__(self, bindings) -> None:
        self.bindings = tuple(bindings)
        self.requested_subject_type = None

    def list_bound_by_subject_type(self, subject_type):
        self.requested_subject_type = subject_type
        return self.bindings


class RecordingProvider:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = []

    def link_to_user(self, provider_menu_id, line_user_id):
        self.calls.append((provider_menu_id, line_user_id))
        return self.outcome


def test_bound_staff_schedules_versioned_menu_binding_intent() -> None:
    outbox = RecordingOutbox()
    binding = LineIdentityBindingSnapshot(
        LineUserId("U-staff"),
        LineIdentityBindingStatus.BOUND,
        ExpectedVersion(2),
        LineBindingSubjectType.STAFF,
        "12",
    )

    schedule_rich_menu_binding(FakeUow(outbox), binding)

    intent = outbox.appended[0]
    assert intent.intent_type == RICH_MENU_BINDING_INTENT
    assert intent.idempotency_identity == "rich-menu-bind:U-staff:2"
    assert json.loads(intent.payload_json)["menu_definition_id"] == "staff_menu"


def test_worker_links_latest_published_menu_and_completes() -> None:
    item = _work_item()
    outbox = RecordingOutbox((item,))
    provider = RecordingProvider(
        LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id="richmenu-staff",
        )
    )
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox), provider, "worker-1", lambda: NOW
    )

    assert worker.run_once() == 1

    assert provider.calls == [("richmenu-staff", LineUserId("U-staff"))]
    assert outbox.completed[0].succeeded is True


def test_worker_uses_publication_pinned_provider_menu() -> None:
    item = _work_item(provider_menu_id="richmenu-union-v3")
    outbox = RecordingOutbox((item,))
    provider = RecordingProvider(_successful_outcome("richmenu-union-v3"))
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox, provider_menu_id=None),
        provider,
        "worker-1",
        lambda: NOW,
    )

    worker.run_once()

    assert provider.calls == [("richmenu-union-v3", LineUserId("U-staff"))]


def test_successful_publication_fans_out_bound_audience_in_same_transaction() -> None:
    binding = _bound_admin("U-union")
    outbox = RecordingOutbox()
    identities = BoundIdentities((binding,))
    unit_of_work = FakeUow(outbox, identities=identities)
    worker = LineRichMenuWorker(
        lambda: unit_of_work,
        RecordingProvider(_successful_outcome("richmenu-union-v3")),
        lambda *_: "image/reference",
        "worker-1",
        lambda: NOW,
    )
    item = SimpleNamespace(
        definition_json=_union_menu_definition(),
        publication=SimpleNamespace(publication_id=LineRichMenuPublicationId(12)),
    )

    worker._record(item, "image/reference", _successful_outcome("richmenu-union-v3"))

    intent = outbox.appended[0]
    assert identities.requested_subject_type is LineBindingSubjectType.ADMIN
    assert intent.idempotency_identity == "rich-menu-rebind:12:U-union"
    assert json.loads(intent.payload_json)["provider_menu_id"] == "richmenu-union-v3"
    assert unit_of_work.committed is True


def test_provider_rejection_is_terminal() -> None:
    outbox = RecordingOutbox((_work_item(),))
    provider = RecordingProvider(
        LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.REJECTED,
            error_code="line_rich_menu_rejected",
            error_message="rejected",
        )
    )
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox), provider, "worker-1", lambda: NOW
    )

    worker.run_once()

    assert outbox.completed[0].retryable is False
    assert outbox.completed[0].error_code == "line_rich_menu_rejected"


def _work_item(provider_menu_id=None):
    payload = {"line_user_id": "U-staff", "menu_definition_id": "staff_menu"}
    if provider_menu_id is not None:
        payload["provider_menu_id"] = provider_menu_id
    return LineOutboxWorkItem(
        7,
        "line_identity",
        "U-staff",
        RICH_MENU_BINDING_INTENT,
        json.dumps(payload),
        0,
        3,
        "worker-1",
        NOW,
    )


def _bound_admin(line_user_id):
    return LineIdentityBindingSnapshot(
        LineUserId(line_user_id),
        LineIdentityBindingStatus.BOUND,
        ExpectedVersion(1),
        LineBindingSubjectType.ADMIN,
        "7",
    )


def _successful_outcome(provider_menu_id):
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType.SUCCESS,
        provider_menu_id=provider_menu_id,
    )


def _union_menu_definition():
    return json.dumps(
        {
            "id": "union_staff_menu",
            "audience_role": "union_staff",
        },
        sort_keys=True,
        separators=(",", ":"),
    )

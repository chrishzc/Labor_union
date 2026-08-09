"""Stage 5 contracts for templates, D+N schedules, and versioned config."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision, LineUserId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.follow_schedule_application import enqueue_follow_schedule
from subsystems.line.message_configuration import (
    LineMessageConfigurationError,
    follow_schedule_steps,
    render_message_template,
)

ROOT = Path(__file__).resolve().parents[3]
FOLLOWED_AT = datetime(2026, 8, 8, 2, 30, tzinfo=timezone.utc)


class FakeUow:
    def __init__(self, **repositories) -> None:
        self.__dict__.update(repositories)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class ConfigurationRepository:
    def __init__(self, snapshots) -> None:
        self.snapshots = dict(snapshots)
        self.applied = []

    def get(self, kind):
        return self.snapshots.get(
            kind,
            LineConfigurationSnapshot(kind, LineConfigurationRevision(0), "{}"),
        )

    def apply(self, command):
        self.applied.append(command)
        snapshot = LineConfigurationSnapshot(
            command.candidate.kind,
            command.candidate.resulting_revision,
            command.candidate.definition_json,
        )
        return SimpleNamespace(outcome="created", snapshot=snapshot)


class RecordingRepository:
    def __init__(self) -> None:
        self.items = []

    def enqueue(self, item):
        self.items.append(item)
        return item

    def append(self, item):
        self.items.append(item)


def _definition(name: str):
    return json.loads((ROOT / "config" / f"{name}.json").read_text("utf-8"))


def _snapshot(kind, name):
    return LineConfigurationSnapshot(
        kind,
        LineConfigurationRevision(1),
        canonical_line_payload_json(_definition(name)),
    )


def test_current_templates_and_schedules_expand_in_taipei_time() -> None:
    templates = _definition("message_templates")
    schedules = _definition("message_schedules")

    steps = follow_schedule_steps(schedules, templates, FOLLOWED_AT)

    assert [step.day for step in steps] == [1, 2, 3]
    assert steps[0].scheduled_at == datetime(2026, 8, 9, 2, tzinfo=timezone.utc)


def test_template_render_requires_declared_required_variables() -> None:
    templates = _definition("message_templates")

    with pytest.raises(LineMessageConfigurationError, match="missing"):
        render_message_template(templates, "register_success", {"case_no": "CASE-1"})

    rendered = render_message_template(
        templates,
        "register_success",
        {"name": "測試客戶", "case_no": "CASE-1"},
    )
    assert "CASE-1" in rendered.payload_json


def test_follow_schedule_uses_stable_non_refollow_idempotency_keys() -> None:
    configurations = ConfigurationRepository(
        {
            LineConfigurationKind.MESSAGE_TEMPLATES: _snapshot(
                LineConfigurationKind.MESSAGE_TEMPLATES,
                "message_templates",
            ),
            LineConfigurationKind.MESSAGE_SCHEDULES: _snapshot(
                LineConfigurationKind.MESSAGE_SCHEDULES,
                "message_schedules",
            ),
        }
    )
    deliveries = RecordingRepository()
    uow = FakeUow(configurations=configurations, delivery_tasks=deliveries)
    inbox = SimpleNamespace(
        event=SimpleNamespace(
            event_id=SimpleNamespace(value="event-follow-1"),
            occurred_at=FOLLOWED_AT,
        )
    )

    count = enqueue_follow_schedule(inbox, uow, LineUserId("U-stage5"))

    assert count == 3
    assert deliveries.items[0].idempotency_key.value == (
        "follow-schedule:U-stage5:new_user_onboarding:d1"
    )


def test_configuration_apply_requires_capability_and_commits_revision() -> None:
    repository = ConfigurationRepository({})
    audit = RecordingRepository()
    uow = FakeUow(configurations=repository, audit=audit)
    application = LineConfigurationApplication(lambda: uow)
    definition = _definition("message_templates")

    result = application.apply(
        kind=LineConfigurationKind.MESSAGE_TEMPLATES,
        expected_revision=LineConfigurationRevision(0),
        definition=definition,
        actor=ActorContext("admin:1", ("line.config.manage",)),
        reason="匯入現有範本",
        idempotency_key=IdempotencyKey("stage5-config:templates:1"),
        correlation_id=CorrelationId("stage5-config:templates:1"),
    )

    assert result.snapshot.revision == LineConfigurationRevision(1)
    assert uow.committed is True
    assert audit.items[0].action == "line.configuration.apply"

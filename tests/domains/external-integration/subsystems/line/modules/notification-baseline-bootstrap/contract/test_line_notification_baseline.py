"""Contract tests for the development-only Task96 notification baseline producer."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from shared_kernel.identities import ActorContext
from api.schemas.line_notification_rules import LineNotificationRulesDefinition
from subsystems.line.notification_baseline import (
    baseline_identities,
    bootstrap_notification_baseline,
    build_baseline_events,
)


class _Notifications:
    def __init__(self) -> None:
        self.events = []

    def register_and_project(self, event) -> int:
        self.events.append(event)
        return len(self.events)


class _UnitOfWork(AbstractContextManager):
    def __init__(self) -> None:
        self.notification_rules = _Notifications()
        self.committed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False


def _actor() -> ActorContext:
    return ActorContext("system:line-task96-baseline", ("line.config.manage",))


def test_baseline_matches_all_26_section_1_3_identities() -> None:
    definition = json.loads(Path("config/notification_rules.json").read_text(encoding="utf-8"))
    typed_definition = LineNotificationRulesDefinition.model_validate(definition)
    assert len(typed_definition.rules) == 13
    assert tuple(rule.event_code for rule in typed_definition.rules) == tuple(
        trigger for _, trigger, _ in baseline_identities()
    )
    events = build_baseline_events(
        target_database="lu_test_line96",
        occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert len(events) == 13
    assert tuple(
        (event.identity, event.event_code, event.facts["recipient_projection"]["selector"])
        for event in events
    ) == baseline_identities()
    assert all(event.source_domain == "line_task96_fixture" for event in events)
    assert all(event.facts["producer_reference"] == "fixture:task96-line14-p0" for event in events)
    assert all(
        event.facts["recipient_projection"]["identity"].startswith("lu_test_")
        for event in events
    )
    assert all(len(event.facts["source_digest"]) == 64 for event in events)


def test_baseline_writer_is_allowlisted_and_single_commit() -> None:
    unit_of_work = _UnitOfWork()
    ids = bootstrap_notification_baseline(
        lambda: unit_of_work,
        target_database="lu_test_line96",
        actor=_actor(),
        occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert ids == tuple(range(1, 14))
    assert unit_of_work.committed is True
    assert len(unit_of_work.notification_rules.events) == 13


def test_baseline_writer_rejects_non_test_target_or_wrong_actor() -> None:
    with pytest.raises(ValueError, match="lu_test"):
        build_baseline_events(target_database="union_db")
    with pytest.raises(PermissionError, match="development-only"):
        bootstrap_notification_baseline(
            _UnitOfWork,
            target_database="lu_test_line96",
            actor=ActorContext("admin", ("line.config.manage",)),
        )

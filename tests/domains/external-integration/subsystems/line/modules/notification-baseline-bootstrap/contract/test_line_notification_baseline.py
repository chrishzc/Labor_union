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


def test_current_catalog_keeps_only_required_notifications_and_real_reminders() -> None:
    definition = json.loads(Path("config/notification_rules.json").read_text(encoding="utf-8"))
    typed_definition = LineNotificationRulesDefinition.model_validate(definition)
    assert tuple(rule.event_code for rule in typed_definition.rules) == (
        "runtime.alert.review_required",
        "complaint.ingress.hold_high_ticket",
        "order.service_start_day",
        "client.second_payment_due",
        "client.second_payment_settled",
        "order.service_completed",
    )
    assert all(rule.event_code != "service_time_checkpoint" for rule in typed_definition.rules)


def test_historical_task96_fixture_keeps_its_provenance_contract() -> None:
    events = build_baseline_events(
        target_database="lu_test_line96",
        occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert len(events) == 12
    # Retiring ordinal 6 must not renumber the remaining immutable fixture subjects.
    alert = next(event for event in events if event.identity == "LU96-M4-SAFE-ALERT-SOURCE-V1")
    assert alert.facts["case_no"] == "LU96-P0-11"
    assert alert.source_aggregate_identity == "task96-line14-p0:11"
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
    assert ids == tuple(range(1, 13))
    assert unit_of_work.committed is True
    assert len(unit_of_work.notification_rules.events) == 12


def test_baseline_writer_rejects_non_test_target_or_wrong_actor() -> None:
    with pytest.raises(ValueError, match="lu_test"):
        build_baseline_events(target_database="union_db")
    with pytest.raises(PermissionError, match="development-only"):
        bootstrap_notification_baseline(
            _UnitOfWork,
            target_database="lu_test_line96",
            actor=ActorContext("admin", ("line.config.manage",)),
        )


@pytest.mark.parametrize("enabled", [False, True])
def test_retired_zero_pool_cannot_be_restored_in_active_configuration(enabled):
    import json
    from pathlib import Path
    from domains.line.notification_rules import validate_notification_rules, LineNotificationRuleError
    from subsystems.line.message_configuration import validate_message_templates, LineMessageConfigurationError
    rules = json.loads(Path("config/notification_rules.json").read_text(encoding="utf-8"))
    rule = dict(rules["rules"][0], id="LU96-M3-ZERO-POOL-RULE-V1", event_code="matching.zero_pool.preview_applied",
                template_id="LU96-M3-ZERO-POOL-CARD-V1", enabled=enabled)
    rules["rules"].append(rule)
    with pytest.raises(LineNotificationRuleError, match="已退役"):
        validate_notification_rules(rules)
    templates = json.loads(Path("config/message_templates.json").read_text(encoding="utf-8"))
    templates["templates"].append(dict(templates["templates"][0], id="LU96-M3-ZERO-POOL-CARD-V1"))
    with pytest.raises(LineMessageConfigurationError, match="已退役"):
        validate_message_templates(templates)


def test_bootstrap_templates_and_schedules_contain_only_current_content():
    from subsystems.line.message_configuration import RETIRED_MESSAGE_TEMPLATE_IDS, validate_message_templates, validate_message_schedules
    templates = json.loads(Path('config/message_templates.json').read_text(encoding='utf-8'))
    schedules = json.loads(Path('config/message_schedules.json').read_text(encoding='utf-8'))
    ids = {item['id'] for item in templates['templates']}
    assert not ids & (RETIRED_MESSAGE_TEMPLATE_IDS | {'0', 'v', '3qlinvqk0s', 'f3uxqwd09'})
    assert all(item['content'] for item in templates['templates'])
    assert schedules['schedules'] == []
    validate_message_templates(templates)
    validate_message_schedules(schedules, templates)


@pytest.mark.parametrize('identifier', ['new_user_d1', 'LU96-M3-MATCH-SUCCESS-CLIENT-CARD-V1', 'LU96-M4-SALARY-PAYABLE-CARD-V1'])
def test_retired_notifications_cannot_be_reintroduced(identifier):
    from subsystems.line.message_configuration import validate_message_templates, LineMessageConfigurationError
    definition = {'templates': [{'id': identifier, 'message_type': 'text', 'content': '舊通知', 'variables': []}]}
    with pytest.raises(LineMessageConfigurationError, match='已退役'):
        validate_message_templates(definition)


@pytest.mark.parametrize('event_code', ['runtime.alert.review_required', 'complaint.ingress.hold_high_ticket'])
@pytest.mark.parametrize('source_domain', ['runtime', 'manual_replay'])
def test_retired_admin_rules_cannot_project_or_send_historical_intents(event_code, source_domain):
    from types import SimpleNamespace
    from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
    from subsystems.line.notification_policy import NotificationSourceEvent, evaluate_notification_rules
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params): calls.append((sql, params))
        def fetchone(self): return {'event_code':event_code, 'source_domain':source_domain}
    repo = MySqlLineNotificationRepository(SimpleNamespace(cursor=Cursor))
    assert repo.manual_replay_delivery_validation_failure(7) == 'line_admin_push_retired'
    assert calls[0][1] == (7,)
    decisions = []
    repo._record_decision = lambda *args: decisions.append(args)
    event = NotificationSourceEvent('old-alert',event_code,False,{},source_domain=source_domain)
    repo._project_rule(7,event,1,{'id':'old-rule','recipient_selector':'admin.review_actor'}, {}, 1)
    assert decisions[0][5:7] == ('suppressed','line_admin_push_retired')
    policy = evaluate_notification_rules(event, {'rules':[{'id':'old-rule','event_code':event_code,'enabled':True,'predicates':[]}]})
    assert [(item.status,item.reason_code) for item in policy] == [('suppressed','line_admin_push_retired')]

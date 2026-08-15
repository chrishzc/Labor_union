"""
File: test_line_notification_rule_administration.py
Description: 驗證刪除通知規則與取消未送 intent 在同一 LINE 交易中完成。
"""

from __future__ import annotations

from contextlib import AbstractContextManager

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.notification_rule_administration import (
    LineNotificationRuleAdministration,
)


class _UnitOfWork(AbstractContextManager):
    def __init__(self) -> None:
        self.configurations = _Configurations()
        self.notification_rules = _Notifications()
        self.audit = _Audit()
        self.committed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False


class _Configurations:
    def get(self, kind):
        return LineConfigurationSnapshot(
            kind,
            LineConfigurationRevision(3),
            canonical_line_payload_json({"rules": [{
                "id": "rule-a", "event_code": "deposit_confirmed",
                "recipient_selector": "case_group", "template_id": "deposit",
                "schedule": {"kind": "immediate"}, "predicates": [],
            }]}),
        )

    def apply(self, command):
        assert command.candidate.resulting_revision == LineConfigurationRevision(4)
        return type("Result", (), {
            "snapshot": LineConfigurationSnapshot(
                LineConfigurationKind.NOTIFICATION_RULES,
                LineConfigurationRevision(4),
                canonical_line_payload_json({"rules": []}),
            )
        })()


class _Notifications:
    def cancel_rule(self, rule_id, *, reason):
        assert (rule_id, reason) == ("rule-a", "notification_rule_deleted")
        return 3


class _Audit:
    def append(self, intent) -> None:
        assert intent.action == "line.notification_rule.delete"


def test_delete_cancels_unsent_intents_in_same_unit_of_work() -> None:
    unit_of_work = _UnitOfWork()
    application = LineNotificationRuleAdministration(lambda: unit_of_work)

    result = application.delete(
        rule_id="rule-a",
        expected_revision=LineConfigurationRevision(3),
        actor=ActorContext("admin-1", ("line.config.manage",)),
        reason="停止規則",
        idempotency_key=IdempotencyKey("notification-rule-delete-1"),
        correlation_id=CorrelationId("notification-rule-delete-1"),
    )

    assert result.revision == LineConfigurationRevision(4)
    assert result.cancelled_intent_count == 3
    assert unit_of_work.committed is True

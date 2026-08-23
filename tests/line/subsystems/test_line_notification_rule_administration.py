"""
File: test_line_notification_rule_administration.py
Description: 驗證刪除通知規則與取消未送 intent 在同一 LINE 交易中完成。
"""

from __future__ import annotations

from contextlib import AbstractContextManager

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationSnapshot,
    build_configuration_candidate,
)
from domains.line.identities import LineConfigurationRevision, LineDeliveryTaskId
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    IdempotencyKey,
    IdempotencyReceipt,
)
from subsystems.line.notification_rule_administration import (
    LineNotificationRuleAdministration,
    LineNotificationRuleMutationError,
    _materialize_current_definition,
)
from subsystems.line.ports import LineNotificationCancellationLineage


class _UnitOfWork(AbstractContextManager):
    def __init__(self) -> None:
        self.events = []
        self.configurations = _Configurations(self.events)
        self.notification_rules = _Notifications(self.events)
        self.delivery_tasks = _DeliveryTasks(self.events)
        self.receipts = _Receipts(self.events)
        self.audit = _Audit(self.events)
        self.committed = False

    def commit(self) -> None:
        self.events.append("commit")
        self.committed = True

    def rollback(self) -> None:
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False


class _Configurations:
    def __init__(self, events) -> None:
        self.events = events

    def get(self, kind):
        return LineConfigurationSnapshot(
            kind,
            LineConfigurationRevision(3),
            canonical_line_payload_json({"rules": [{
                "id": "rule_a", "event_code": "deposit_confirmed",
                "recipient_selector": "case_group", "template_id": "deposit",
                "schedule": {"kind": "immediate"}, "predicates": [],
            }]}),
        )

    def apply(self, command):
        self.events.append("configuration.apply")
        assert command.candidate.resulting_revision == LineConfigurationRevision(4)
        return type("Result", (), {
            "snapshot": LineConfigurationSnapshot(
                LineConfigurationKind.NOTIFICATION_RULES,
                LineConfigurationRevision(4),
                canonical_line_payload_json({"rules": []}),
            )
        })()


class _EnabledConfigurations(_Configurations):
    def get(self, kind):
        return LineConfigurationSnapshot(
            kind,
            LineConfigurationRevision(3),
            canonical_line_payload_json({"rules": [{
                "id": "rule_a",
                "event_code": "deposit_confirmed",
                "recipient_selector": "case_group",
                "template_id": "deposit",
                "enabled": True,
                "schedule": {"kind": "immediate"},
                "frequency": {"kind": "once"},
                "predicates": [],
            }]}),
        )


class _Notifications:
    def __init__(self, events) -> None:
        self.events = events

    def lock_and_cancel_rule_intents(self, rule_id, *, reason):
        self.events.append("notification.lock_cancel")
        assert rule_id == "rule_a"
        assert reason in {"notification_rule_delete", "notification_rule_save"}
        return LineNotificationCancellationLineage(
            (10, 11, 12),
            (LineDeliveryTaskId(20), LineDeliveryTaskId(21)),
        )


class _DeliveryTasks:
    def __init__(self, events) -> None:
        self.events = events

    def cancel_pending_for_notification_rule(self, task_ids, *, reason):
        self.events.append("delivery.cancel")
        assert reason in {"notification_rule_delete", "notification_rule_save"}
        return task_ids


class _Receipts:
    def __init__(self, events) -> None:
        self.events = events
        self.receipt = None

    def get(self, key):
        if self.receipt is not None and self.receipt.key == key:
            return self.receipt
        return None

    def append(self, receipt):
        self.events.append("receipt.append")
        self.receipt = receipt


class _Audit:
    def __init__(self, events) -> None:
        self.events = events

    def append(self, intent) -> None:
        self.events.append("audit.append")
        assert intent.action in {
            "line.notification_rule.delete",
            "line.notification_rule.save",
        }


def test_delete_cancels_unsent_intents_in_same_unit_of_work() -> None:
    unit_of_work = _UnitOfWork()
    application = LineNotificationRuleAdministration(lambda: unit_of_work)
    current = unit_of_work.configurations.get(LineConfigurationKind.NOTIFICATION_RULES)
    preview = build_configuration_candidate(
        kind=LineConfigurationKind.NOTIFICATION_RULES,
        current_revision=current.revision,
        expected_revision=current.revision,
        definition={"rules": []},
    )

    result = application.delete(
        rule_id="rule_a",
        expected_revision=LineConfigurationRevision(3),
        preview_fingerprint=preview.fingerprint,
        actor=ActorContext("admin-1", ("line.config.manage",)),
        reason="停止規則",
        idempotency_key=IdempotencyKey("notification-rule-delete-1"),
        correlation_id=CorrelationId("notification-rule-delete-1"),
    )

    assert result.revision == LineConfigurationRevision(4)
    assert result.cancelled_intent_count == 3
    assert result.cancelled_task_count == 2
    assert unit_of_work.committed is True
    assert unit_of_work.events == [
        "configuration.apply",
        "notification.lock_cancel",
        "delivery.cancel",
        "receipt.append",
        "audit.append",
        "commit",
    ]

    unit_of_work.events.clear()
    replay = application.delete(
        rule_id="rule_a",
        expected_revision=LineConfigurationRevision(3),
        preview_fingerprint=preview.fingerprint,
        actor=ActorContext("admin-1", ("line.config.manage",)),
        reason="停止規則",
        idempotency_key=IdempotencyKey("notification-rule-delete-1"),
        correlation_id=CorrelationId("notification-rule-delete-1"),
    )
    assert replay == result
    assert unit_of_work.events == []

    with pytest.raises(LineNotificationRuleMutationError, match="different payload"):
        application.delete(
            rule_id="rule_a",
            expected_revision=LineConfigurationRevision(3),
            preview_fingerprint=type(preview.fingerprint)("f" * 64),
            actor=ActorContext("admin-1", ("line.config.manage",)),
            reason="停止規則",
            idempotency_key=IdempotencyKey("notification-rule-delete-1"),
            correlation_id=CorrelationId("notification-rule-delete-1"),
        )

    with pytest.raises(LineNotificationRuleMutationError, match="different payload"):
        application.delete(
            rule_id="rule_a",
            expected_revision=LineConfigurationRevision(3),
            preview_fingerprint=preview.fingerprint,
            actor=ActorContext("admin-1", ("line.config.manage",)),
            reason="另一個理由",
            idempotency_key=IdempotencyKey("notification-rule-delete-1"),
            correlation_id=CorrelationId("notification-rule-delete-1"),
        )

    with pytest.raises(LineNotificationRuleMutationError, match="different payload"):
        application.delete(
            rule_id="rule_a",
            expected_revision=LineConfigurationRevision(3),
            preview_fingerprint=preview.fingerprint,
            actor=ActorContext("admin-1", ("line.config.manage",)),
            reason="停止規則",
            idempotency_key=IdempotencyKey("notification-rule-delete-1"),
            correlation_id=CorrelationId("another-correlation"),
        )

    stored = unit_of_work.receipts.receipt
    for result_reference in (
        "line-notification-delete|rule_a|4|-1|2",
        "line-notification-delete|rule_a|04|00|2",
    ):
        unit_of_work.receipts.receipt = IdempotencyReceipt(
            stored.key,
            stored.payload_fingerprint,
            result_reference,
        )
        with pytest.raises(LineNotificationRuleMutationError, match="receipt is invalid"):
            application.delete(
                rule_id="rule_a",
                expected_revision=LineConfigurationRevision(3),
                preview_fingerprint=preview.fingerprint,
                actor=ActorContext("admin-1", ("line.config.manage",)),
                reason="停止規則",
                idempotency_key=IdempotencyKey("notification-rule-delete-1"),
                correlation_id=CorrelationId("notification-rule-delete-1"),
            )


def test_empty_genesis_materializes_to_closed_empty_rule_collection() -> None:
    assert _materialize_current_definition("{}") == {"rules": []}


def test_save_disabling_enabled_rule_uses_same_atomic_owner_order() -> None:
    unit_of_work = _UnitOfWork()
    unit_of_work.configurations = _EnabledConfigurations(unit_of_work.events)
    application = LineNotificationRuleAdministration(lambda: unit_of_work)
    definition = {"rules": [{
        "id": "rule_a",
        "event_code": "deposit_confirmed",
        "recipient_selector": "case_group",
        "template_id": "deposit",
        "enabled": False,
        "schedule": {"kind": "immediate"},
        "frequency": {"kind": "once"},
        "predicates": [],
    }]}
    preview = build_configuration_candidate(
        kind=LineConfigurationKind.NOTIFICATION_RULES,
        current_revision=LineConfigurationRevision(3),
        expected_revision=LineConfigurationRevision(3),
        definition=definition,
    )

    result = application.save(
        definition=definition,
        expected_revision=LineConfigurationRevision(3),
        preview_fingerprint=preview.fingerprint,
        actor=ActorContext("admin-1", ("line.config.manage",)),
        reason="停用規則",
        idempotency_key=IdempotencyKey("notification-rule-save-1"),
        correlation_id=CorrelationId("notification-rule-save-1"),
    )

    assert result.cancelled_intent_count == 3
    assert result.cancelled_task_count == 2
    assert unit_of_work.events == [
        "configuration.apply",
        "notification.lock_cancel",
        "delivery.cancel",
        "receipt.append",
        "audit.append",
        "commit",
    ]

"""
File: notification_rule_administration.py
Description: 以單一 LINE UoW 刪除通知規則 revision，並取消所有尚未送出的舊意圖。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
    build_configuration_candidate,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.configuration_contracts import ApplyLineConfigurationCommand
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class DeleteNotificationRuleResult:
    rule_id: str
    revision: LineConfigurationRevision
    cancelled_intent_count: int


class LineNotificationRuleAdministration:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def delete(
        self,
        *,
        rule_id: str,
        expected_revision: LineConfigurationRevision,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> DeleteNotificationRuleResult:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.configurations.get(
                LineConfigurationKind.NOTIFICATION_RULES
            )
            if current.revision != expected_revision:
                raise LineConfigurationRevisionConflict(
                    "LINE notification rule revision is stale"
                )
            definition = json.loads(current.definition_json)
            rules = definition.get("rules")
            if not isinstance(rules, list):
                raise ValueError("notification rules configuration is invalid")
            remaining = [
                rule for rule in rules
                if isinstance(rule, dict) and rule.get("id") != rule_id
            ]
            if len(remaining) == len(rules):
                raise LookupError("notification rule not found")
            candidate = build_configuration_candidate(
                kind=LineConfigurationKind.NOTIFICATION_RULES,
                current_revision=current.revision,
                expected_revision=expected_revision,
                definition={**definition, "rules": remaining},
            )
            result = unit_of_work.configurations.apply(
                ApplyLineConfigurationCommand(
                    candidate, actor, reason, idempotency_key, correlation_id
                )
            )
            cancelled = unit_of_work.notification_rules.cancel_rule(
                rule_id, reason="notification_rule_deleted"
            )
            unit_of_work.audit.append(
                LineAuditIntent(
                    "line.notification_rule.delete",
                    actor.actor_id,
                    "line_notification_rule",
                    rule_id,
                )
            )
            unit_of_work.commit()
        return DeleteNotificationRuleResult(
            rule_id, result.snapshot.revision, cancelled
        )


__all__ = ["DeleteNotificationRuleResult", "LineNotificationRuleAdministration"]

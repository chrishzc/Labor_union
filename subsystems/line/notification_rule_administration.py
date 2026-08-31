"""
File: notification_rule_administration.py
Description: 以單一 LINE UoW 儲存或刪除通知規則，並依 owner 邊界取消 intent 與 delivery task。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Mapping

from domains.line.configuration import (
    LineConfigurationKind,
    build_configuration_candidate,
)
from domains.line.identities import LineConfigurationRevision
from domains.line.notification_rules import materialize_notification_rules_definition
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    IdempotencyKey,
    IdempotencyReceipt,
)
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.configuration_contracts import ApplyLineConfigurationCommand
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort
from subsystems.line.notification_failure_current_fact import (
    append_line_notification_failure_rechecks,
)


class LineNotificationRuleMutationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SaveNotificationRulesResult:
    revision: LineConfigurationRevision
    preview_fingerprint: PreviewFingerprint
    cancelled_intent_count: int
    cancelled_task_count: int


@dataclass(frozen=True, slots=True)
class DeleteNotificationRuleResult:
    rule_id: str
    revision: LineConfigurationRevision
    preview_fingerprint: PreviewFingerprint
    cancelled_intent_count: int
    cancelled_task_count: int


class LineNotificationRuleAdministration:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def save(
        self,
        *,
        definition: Mapping[str, object],
        expected_revision: LineConfigurationRevision,
        preview_fingerprint: PreviewFingerprint,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> SaveNotificationRulesResult:
        normalized = materialize_notification_rules_definition(definition)
        result = self._mutate(
            action="save",
            rule_id=None,
            definition=normalized,
            expected_revision=expected_revision,
            preview_fingerprint=preview_fingerprint,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        return SaveNotificationRulesResult(
            result.revision,
            result.preview_fingerprint,
            result.cancelled_intent_count,
            result.cancelled_task_count,
        )

    def delete(
        self,
        *,
        rule_id: str,
        expected_revision: LineConfigurationRevision,
        preview_fingerprint: PreviewFingerprint,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> DeleteNotificationRuleResult:
        return self._mutate(
            action="delete",
            rule_id=rule_id,
            definition=None,
            expected_revision=expected_revision,
            preview_fingerprint=preview_fingerprint,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def _mutate(
        self,
        *,
        action: str,
        rule_id: str | None,
        definition: Mapping[str, object] | None,
        expected_revision: LineConfigurationRevision,
        preview_fingerprint: PreviewFingerprint,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> SaveNotificationRulesResult | DeleteNotificationRuleResult:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        command_fingerprint = _command_fingerprint(
            action,
            rule_id,
            expected_revision,
            preview_fingerprint,
            definition,
            actor,
            reason,
            correlation_id,
        )
        with self._unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.receipts.get(idempotency_key)
            if existing is not None:
                if action == "delete":
                    return _delete_replay(
                        existing,
                        command_fingerprint,
                        rule_id or "",
                        preview_fingerprint,
                    )
                return _save_replay(
                    existing,
                    command_fingerprint,
                    preview_fingerprint,
                )
            current = unit_of_work.configurations.get(
                LineConfigurationKind.NOTIFICATION_RULES
            )
            previous = _materialize_current_definition(current.definition_json)
            resulting = definition
            if action == "delete":
                if rule_id is None:
                    raise LineNotificationRuleMutationError(
                        "line_notification_rule_command_invalid",
                        "notification rule delete target is required",
                    )
                remaining = [
                    rule for rule in previous["rules"] if rule["id"] != rule_id
                ]
                if len(remaining) == len(previous["rules"]):
                    raise LineNotificationRuleMutationError(
                        "line_notification_rule_not_found",
                        "notification rule not found",
                    )
                resulting = {"rules": remaining}
            if resulting is None:
                raise LineNotificationRuleMutationError(
                    "line_notification_rule_command_invalid",
                    "notification rule definition is required",
                )
            candidate = build_configuration_candidate(
                kind=LineConfigurationKind.NOTIFICATION_RULES,
                current_revision=current.revision,
                expected_revision=expected_revision,
                definition=resulting,
            )
            if candidate.fingerprint != preview_fingerprint:
                raise LineNotificationRuleMutationError(
                    "line_notification_rule_preview_mismatch",
                    "notification rule preview fingerprint is stale",
                )
            cancellation_ids = _rules_requiring_cancellation(previous, resulting)
            affected_event_codes = _affected_event_codes(previous, resulting)
            result = unit_of_work.configurations.apply(
                ApplyLineConfigurationCommand(
                    candidate, actor, reason, idempotency_key, correlation_id
                )
            )
            cancelled_intents = 0
            cancelled_tasks = 0
            for cancellation_rule_id in cancellation_ids:
                lineage = unit_of_work.notification_rules.lock_and_cancel_rule_intents(
                    cancellation_rule_id,
                    reason=f"notification_rule_{action}",
                )
                task_ids = unit_of_work.delivery_tasks.cancel_pending_for_notification_rule(
                    lineage.task_ids,
                    reason=f"notification_rule_{action}",
                )
                if task_ids != lineage.task_ids:
                    raise LineNotificationRuleMutationError(
                        "line_notification_rule_cancellation_conflict",
                        "notification task cancellation did not match intent lineage",
                    )
                cancelled_intents += len(lineage.intent_ids)
                cancelled_tasks += len(task_ids)
            target_reader = getattr(
                unit_of_work.notification_rules,
                "line006_recheck_targets_for_event_codes",
                None,
            )
            targets = (
                target_reader(affected_event_codes)
                if callable(target_reader)
                else ()
            )
            append_line_notification_failure_rechecks(
                unit_of_work,
                targets,
                cause_identity=f"notification-rules:{idempotency_key.value}",
            )
            receipt = IdempotencyReceipt(
                idempotency_key,
                command_fingerprint,
                _result_reference(
                    action,
                    rule_id,
                    result.snapshot.revision,
                    cancelled_intents,
                    cancelled_tasks,
                ),
            )
            unit_of_work.receipts.append(receipt)
            unit_of_work.audit.append(
                LineAuditIntent(
                    f"line.notification_rule.{action}",
                    actor.actor_id,
                    "line_notification_rule" if rule_id else "line_notification_rules",
                    rule_id or "catalog",
                )
            )
            unit_of_work.commit()
        if action == "delete":
            return DeleteNotificationRuleResult(
                rule_id or "",
                result.snapshot.revision,
                candidate.fingerprint,
                cancelled_intents,
                cancelled_tasks,
            )
        return SaveNotificationRulesResult(
            result.snapshot.revision,
            candidate.fingerprint,
            cancelled_intents,
            cancelled_tasks,
        )


def _rules_requiring_cancellation(
    previous: Mapping[str, object],
    resulting: Mapping[str, object],
) -> tuple[str, ...]:
    before = {rule["id"]: rule for rule in previous["rules"]}
    after = {rule["id"]: rule for rule in resulting["rules"]}
    return tuple(sorted(
        identifier for identifier, rule in before.items()
        if identifier not in after
        or (rule["enabled"] is True and after[identifier]["enabled"] is False)
    ))


def _affected_event_codes(
    previous: Mapping[str, object],
    resulting: Mapping[str, object],
) -> tuple[str, ...]:
    before = {rule["id"]: rule for rule in previous["rules"]}
    after = {rule["id"]: rule for rule in resulting["rules"]}
    changed_ids = {
        identifier
        for identifier in set(before) | set(after)
        if before.get(identifier) != after.get(identifier)
    }
    return tuple(sorted({
        str(rule["event_code"])
        for identifier in changed_ids
        for rule in (before.get(identifier), after.get(identifier))
        if isinstance(rule, Mapping) and isinstance(rule.get("event_code"), str)
    }))


def _materialize_current_definition(definition_json: str) -> dict[str, object]:
    value = json.loads(definition_json)
    if value == {}:
        value = {"rules": []}
    if not isinstance(value, dict):
        raise LineNotificationRuleMutationError(
            "line_notification_rule_current_state_invalid",
            "notification rule current state is invalid",
        )
    return materialize_notification_rules_definition(value)


def _command_fingerprint(
    action: str,
    rule_id: str | None,
    expected_revision: LineConfigurationRevision,
    preview: PreviewFingerprint,
    definition: Mapping[str, object] | None,
    actor: ActorContext,
    reason: str,
    correlation_id: CorrelationId,
) -> PreviewFingerprint:
    payload = {
        "action": action,
        "rule_id": rule_id,
        "expected_revision": expected_revision.value,
        "preview_fingerprint": preview.value,
        "definition": definition,
        "actor_id": actor.actor_id,
        "permission_scope": actor.permission_scope,
        "reason": reason,
        "correlation_id": correlation_id.value,
    }
    return fingerprint_payload(payload)


def _result_reference(
    action: str,
    rule_id: str | None,
    revision: LineConfigurationRevision,
    intents: int,
    tasks: int,
) -> str:
    identity = rule_id or "catalog"
    return f"line-notification-{action}|{identity}|{revision.value}|{intents}|{tasks}"


def _replay_values(
    receipt: IdempotencyReceipt,
    command_fingerprint: PreviewFingerprint,
    expected_action: str,
    expected_identity: str,
) -> tuple[LineConfigurationRevision, int, int]:
    if receipt.payload_fingerprint != command_fingerprint:
        raise LineNotificationRuleMutationError(
            "line_notification_rule_idempotency_conflict",
            "notification rule idempotency key has a different payload",
        )
    parts = receipt.result_reference.split("|")
    if len(parts) != 5 or parts[0] != f"line-notification-{expected_action}" or parts[1] != expected_identity:
        raise LineNotificationRuleMutationError(
            "line_notification_rule_receipt_invalid",
            "notification rule receipt does not match the command",
        )
    number_parts = tuple(parts[2:])
    if any(not part or any(character not in "0123456789" for character in part) for part in number_parts):
        raise LineNotificationRuleMutationError(
            "line_notification_rule_receipt_invalid",
            "notification rule receipt is invalid",
        )
    revision_value, intents, tasks = (int(part) for part in number_parts)
    if (
        tuple(str(value) for value in (revision_value, intents, tasks)) != number_parts
        or revision_value < 1
        or intents < 0
        or tasks < 0
    ):
        raise LineNotificationRuleMutationError(
            "line_notification_rule_receipt_invalid",
            "notification rule receipt is invalid",
        )
    return LineConfigurationRevision(revision_value), intents, tasks


def _save_replay(receipt, command_fingerprint, preview_fingerprint):
    revision, intents, tasks = _replay_values(
        receipt, command_fingerprint, "save", "catalog"
    )
    return SaveNotificationRulesResult(
        revision, preview_fingerprint, intents, tasks
    )


def _delete_replay(receipt, command_fingerprint, rule_id, preview_fingerprint):
    revision, intents, tasks = _replay_values(
        receipt, command_fingerprint, "delete", rule_id
    )
    return DeleteNotificationRuleResult(
        rule_id,
        revision,
        preview_fingerprint,
        intents,
        tasks,
    )


__all__ = [
    "DeleteNotificationRuleResult",
    "LineNotificationRuleAdministration",
    "LineNotificationRuleMutationError",
    "SaveNotificationRulesResult",
]

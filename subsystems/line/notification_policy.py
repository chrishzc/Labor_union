"""
File: notification_policy.py
Description: 以白名單規則評估不可變來源事件，產生可稽核通知決策而不直接發送 LINE。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


@dataclass(frozen=True, slots=True)
class NotificationSourceEvent:
    identity: str
    event_code: str
    historical_silent: bool
    facts: Mapping[str, object]
    source_domain: str = "unknown"
    source_aggregate_type: str = "unknown"
    source_aggregate_identity: str = "unknown"
    source_version: int = 1
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    rule_id: str
    status: str
    reason_code: str


def evaluate_notification_rules(
    event: NotificationSourceEvent,
    definition: Mapping[str, object],
) -> tuple[NotificationDecision, ...]:
    """Return one terminal decision per matching rule without provider side effects."""
    rules = definition.get("rules")
    if not isinstance(rules, list):
        raise ValueError("notification rules must be configured")
    decisions: list[NotificationDecision] = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("event_code") != event.event_code:
            continue
        rule_id = str(rule.get("id", ""))
        if event.historical_silent:
            decisions.append(NotificationDecision(rule_id, "suppressed", "historical_source_silent"))
        elif rule.get("enabled", False) is not True:
            decisions.append(NotificationDecision(rule_id, "suppressed", "rule_shadow_mode"))
        elif _predicates_match(rule.get("predicates", []), event.facts):
            decisions.append(NotificationDecision(rule_id, "intent_created", "rule_matched"))
        else:
            decisions.append(NotificationDecision(rule_id, "suppressed", "prerequisite_not_satisfied"))
    return tuple(decisions)


def _predicates_match(predicates: object, facts: Mapping[str, object]) -> bool:
    if not isinstance(predicates, list):
        return False
    checks = {
        "requires_cooking_true": facts.get("requires_cooking") is True,
        "baby_log_missing": facts.get("baby_log_completed") is False,
        "beclass_missing": facts.get("beclass_completed") is False,
    }
    return all(checks.get(str(predicate), False) for predicate in predicates)


__all__ = ["NotificationDecision", "NotificationSourceEvent", "evaluate_notification_rules"]

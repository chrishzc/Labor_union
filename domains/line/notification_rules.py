"""
File: notification_rules.py
Description: 驗證可配置 LINE 通知規則的白名單事件、條件與收件人契約。
"""

from __future__ import annotations

import re
from collections.abc import Mapping


class LineNotificationRuleError(ValueError):
    """Raised when a notification-rule definition is unsafe or invalid."""


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_EVENT_CODES = frozenset(
    {
        "order_lifecycle_transition",
        "service_time_checkpoint",
        "beclass_completion_changed",
        "deposit_confirmed",
    }
)
_RECIPIENT_SELECTORS = frozenset(
    {"client", "assigned_caregiver", "case_group"}
)
_SCHEDULE_KINDS = frozenset(
    {"immediate", "relative_service_time", "service_end"}
)
_FREQUENCY_KINDS = frozenset({"once", "recurring_bounded"})
_PREDICATE_CODES = frozenset(
    {"requires_cooking_true", "baby_log_missing", "beclass_missing"}
)


def validate_notification_rules(definition: Mapping[str, object]) -> None:
    """Validate a configuration snapshot without evaluating business facts."""
    rules = definition.get("rules")
    if not isinstance(rules, list) or any(not isinstance(item, dict) for item in rules):
        raise LineNotificationRuleError("notification rules must be a list of objects")
    identifiers: set[str] = set()
    for rule in rules:
        identifier = _identifier(rule.get("id"), "rule id")
        if identifier in identifiers:
            raise LineNotificationRuleError("notification rule ids must be unique")
        identifiers.add(identifier)
        if rule.get("event_code") not in _EVENT_CODES:
            raise LineNotificationRuleError("notification event is not registered")
        if rule.get("recipient_selector") not in _RECIPIENT_SELECTORS:
            raise LineNotificationRuleError("notification recipient selector is invalid")
        enabled = rule.get("enabled", False)
        if not isinstance(enabled, bool):
            raise LineNotificationRuleError("notification enabled state is invalid")
        _identifier(rule.get("template_id"), "template id")
        schedule = rule.get("schedule")
        if not isinstance(schedule, dict) or schedule.get("kind") not in _SCHEDULE_KINDS:
            raise LineNotificationRuleError("notification schedule is invalid")
        if schedule.get("kind") == "relative_service_time":
            offset = schedule.get("offset_seconds")
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                raise LineNotificationRuleError("notification schedule offset is invalid")
        frequency = rule.get("frequency", {"kind": "once"})
        if not isinstance(frequency, dict) or frequency.get("kind") not in _FREQUENCY_KINDS:
            raise LineNotificationRuleError("notification frequency is invalid")
        if frequency.get("kind") == "recurring_bounded":
            maximum = frequency.get("maximum_occurrences")
            interval_days = frequency.get("interval_days")
            if (
                not isinstance(maximum, int)
                or isinstance(maximum, bool)
                or maximum < 1
                or not isinstance(interval_days, int)
                or isinstance(interval_days, bool)
                or interval_days < 1
            ):
                raise LineNotificationRuleError("recurring notification maximum is invalid")
        predicates = rule.get("predicates", [])
        if not isinstance(predicates, list) or any(item not in _PREDICATE_CODES for item in predicates):
            raise LineNotificationRuleError("notification predicate is not registered")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise LineNotificationRuleError(f"{field} is invalid")
    return value


__all__ = ["LineNotificationRuleError", "validate_notification_rules"]

"""
File: notification_rules.py
Description: 驗證可配置 LINE 通知規則的白名單事件、條件與收件人契約。
"""

from __future__ import annotations

import re
from collections.abc import Mapping


class LineNotificationRuleError(ValueError):
    """Raised when a notification-rule definition is unsafe or invalid."""


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_EVENT_CODES = frozenset(
    {
        "order_lifecycle_transition",
        "service_time_checkpoint",
        "beclass_completion_changed",
        "deposit_confirmed",
        "gateway.identity_mismatch.second_attempt",
        "scheduling.leave.extension_requested",
        "staff.retirement.committed",
        "router.deterministic.reply_committed",
        "feedback.resolved.recorded",
        "feedback.unresolved.recorded",
        "matching.zero_pool.preview_applied",
        "matching.decision.committed.client",
        "matching.decision.committed.staff",
        "client.leave.extension_agreed",
        "client.leave.extension_rejected",
        "runtime.alert.review_required",
        "complaint.ingress.hold_high_ticket",
        "payroll.substitute.obligation_projected",
    }
)
_RECIPIENT_SELECTORS = frozenset(
    {
        "client", "assigned_caregiver", "case_group",
        "customer_service.ticket_owner",
        "client.bound_case",
        "staff.binding_owner",
        "conversation.bound_actor",
        "matching.request.participants",
        "assignment.client_snapshot",
        "assignment.staff_snapshot",
        "scheduling.owner",
        "admin.review_actor",
        "customer_service.claim_owner",
        "staff_payables.anomaly_owner",
    }
)
_SCHEDULE_KINDS = frozenset(
    {"immediate", "relative_service_time", "service_end"}
)
_FREQUENCY_KINDS = frozenset({"once", "recurring_bounded"})
_PREDICATE_CODES = frozenset(
    {"requires_cooking_true", "baby_log_missing", "beclass_missing"}
)
_ROOT_FIELDS = frozenset({"rules"})
_RULE_FIELDS = frozenset({
    "id", "event_code", "recipient_selector", "template_id", "enabled",
    "schedule", "frequency", "predicates",
})


def validate_notification_rules(definition: Mapping[str, object]) -> None:
    """Validate a configuration snapshot without evaluating business facts."""
    materialize_notification_rules_definition(definition)


def materialize_notification_rules_definition(
    definition: Mapping[str, object],
) -> dict[str, object]:
    """Return the canonical closed rule grammar with every optional default present."""
    _require_exact_fields(definition, _ROOT_FIELDS, "notification rule definition")
    rules = definition.get("rules")
    if not isinstance(rules, list) or any(not isinstance(item, dict) for item in rules):
        raise LineNotificationRuleError("notification rules must be a list of objects")
    identifiers: set[str] = set()
    materialized: list[dict[str, object]] = []
    for rule in rules:
        _require_exact_fields(rule, _RULE_FIELDS, "notification rule", optional={"enabled", "frequency", "predicates"})
        identifier = _identifier(rule.get("id"), "rule id")
        if identifier in identifiers:
            raise LineNotificationRuleError("notification rule ids must be unique")
        identifiers.add(identifier)
        event_code = _identifier(rule.get("event_code"), "notification event")
        if rule.get("recipient_selector") not in _RECIPIENT_SELECTORS:
            raise LineNotificationRuleError("notification recipient selector is invalid")
        enabled = rule.get("enabled", False)
        if not isinstance(enabled, bool):
            raise LineNotificationRuleError("notification enabled state is invalid")
        if enabled and event_code not in _EVENT_CODES:
            raise LineNotificationRuleError("notification event is not registered")
        _identifier(rule.get("template_id"), "template id")
        schedule = _materialize_schedule(rule.get("schedule"))
        frequency = _materialize_frequency(rule.get("frequency", {"kind": "once"}))
        predicates = rule.get("predicates", [])
        if not isinstance(predicates, list) or any(item not in _PREDICATE_CODES for item in predicates):
            raise LineNotificationRuleError("notification predicate is not registered")
        if len(predicates) != len(set(predicates)):
            raise LineNotificationRuleError("notification predicates must be unique")
        materialized.append({
            "id": identifier,
            "event_code": event_code,
            "recipient_selector": rule["recipient_selector"],
            "template_id": rule["template_id"],
            "enabled": enabled,
            "schedule": schedule,
            "frequency": frequency,
            "predicates": list(predicates),
        })
    return {"rules": materialized}


def registered_notification_event_codes() -> frozenset[str]:
    return _EVENT_CODES


def _materialize_schedule(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("kind") not in _SCHEDULE_KINDS:
        raise LineNotificationRuleError("notification schedule is invalid")
    kind = value["kind"]
    fields = {"kind", "offset_seconds"} if kind == "relative_service_time" else {"kind"}
    _require_exact_fields(value, frozenset(fields), "notification schedule")
    if kind == "relative_service_time":
        offset = value.get("offset_seconds")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise LineNotificationRuleError("notification schedule offset is invalid")
        return {"kind": kind, "offset_seconds": offset}
    return {"kind": kind}


def _materialize_frequency(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("kind") not in _FREQUENCY_KINDS:
        raise LineNotificationRuleError("notification frequency is invalid")
    kind = value["kind"]
    if kind == "once":
        _require_exact_fields(value, frozenset({"kind"}), "notification frequency")
        return {"kind": kind}
    _require_exact_fields(
        value,
        frozenset({"kind", "maximum_occurrences", "interval_days"}),
        "recurring notification frequency",
    )
    maximum = value.get("maximum_occurrences")
    interval_days = value.get("interval_days")
    if (
        not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or maximum < 1
        or not isinstance(interval_days, int)
        or isinstance(interval_days, bool)
        or interval_days < 1
    ):
        raise LineNotificationRuleError("recurring notification maximum is invalid")
    return {"kind": kind, "maximum_occurrences": maximum, "interval_days": interval_days}


def _require_exact_fields(
    value: Mapping[str, object],
    allowed: frozenset[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    actual = frozenset(value)
    required = allowed - frozenset(optional or ())
    if not required <= actual or not actual <= allowed:
        raise LineNotificationRuleError(f"{label} fields are invalid")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise LineNotificationRuleError(f"{field} is invalid")
    return value


__all__ = [
    "LineNotificationRuleError",
    "materialize_notification_rules_definition",
    "registered_notification_event_codes",
    "validate_notification_rules",
]

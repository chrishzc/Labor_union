"""Validate LINE message configuration and render immutable task payloads."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationSnapshot
from domains.line.delivery import LineMessageKind

_VARIABLE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")
_SEND_TIME = re.compile(r"^(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)$")


class LineMessageConfigurationError(ValueError):
    """Raised when a template or schedule definition is invalid."""


@dataclass(frozen=True, slots=True)
class RenderedLineMessage:
    message_kind: LineMessageKind
    payload_json: str


@dataclass(frozen=True, slots=True)
class FollowScheduleStep:
    schedule_id: str
    day: int
    template_id: str
    scheduled_at: datetime
    restart_on_refollow: bool


def configuration_definition(snapshot: LineConfigurationSnapshot) -> dict[str, object]:
    value = json.loads(snapshot.definition_json)
    if not isinstance(value, dict):
        raise LineMessageConfigurationError("LINE configuration must be an object")
    return value


def validate_message_templates(definition: Mapping[str, object]) -> None:
    templates = _object_list(definition, "templates")
    identifiers: set[str] = set()
    for template in templates:
        identifier = _identifier(template.get("id"), "template id")
        if identifier in identifiers:
            raise LineMessageConfigurationError("message template ids must be unique")
        identifiers.add(identifier)
        message_type = template.get("message_type")
        content = template.get("content")
        if message_type == "text" and not isinstance(content, str):
            raise LineMessageConfigurationError("text template content must be text")
        if message_type == "flex" and not isinstance(content, dict):
            raise LineMessageConfigurationError("flex template content must be an object")
        if message_type not in {"text", "flex"}:
            raise LineMessageConfigurationError("unsupported message template type")
        declared = _declared_variables(template)
        used = _variables_in_value(content)
        if not used.issubset(declared):
            raise LineMessageConfigurationError(
                f"template {identifier} uses undeclared variables"
            )


def validate_message_schedules(
    definition: Mapping[str, object],
    templates: Mapping[str, object],
) -> None:
    validate_message_templates(templates)
    available_templates = {
        _identifier(item.get("id"), "template id")
        for item in _object_list(templates, "templates")
        if item.get("enabled", True) is True
    }
    timezone_name = definition.get("timezone", "Asia/Taipei")
    _timezone(timezone_name)
    identifiers: set[str] = set()
    for schedule in _object_list(definition, "schedules"):
        schedule_id = _identifier(schedule.get("id"), "schedule id")
        if schedule_id in identifiers:
            raise LineMessageConfigurationError("message schedule ids must be unique")
        identifiers.add(schedule_id)
        if schedule.get("trigger") != "follow":
            raise LineMessageConfigurationError("unsupported message schedule trigger")
        days: set[int] = set()
        for step in _object_list(schedule, "steps"):
            day = step.get("day")
            if not isinstance(day, int) or isinstance(day, bool) or day < 0:
                raise LineMessageConfigurationError("schedule day must be nonnegative")
            if day in days:
                raise LineMessageConfigurationError(
                    f"schedule {schedule_id} contains duplicate days"
                )
            days.add(day)
            if _identifier(step.get("template_id"), "template id") not in available_templates:
                raise LineMessageConfigurationError("schedule references unavailable template")
            _parsed_send_time(step.get("send_time"))


def render_message_template(
    definition: Mapping[str, object],
    template_id: str,
    variables: Mapping[str, object] | None = None,
) -> RenderedLineMessage:
    validate_message_templates(definition)
    template = next(
        (
            item
            for item in _object_list(definition, "templates")
            if item.get("id") == template_id
        ),
        None,
    )
    if template is None or template.get("enabled", True) is not True:
        raise LineMessageConfigurationError("message template is unavailable")
    supplied = dict(variables or {})
    declared = _declared_variables(template)
    required = {
        str(item["name"])
        for item in _object_list(template, "variables", required=False)
        if item.get("required", False) is True
    }
    missing = sorted(required.difference(supplied))
    if missing:
        raise LineMessageConfigurationError(
            "missing message template variables: " + ", ".join(missing)
        )
    unexpected = sorted(set(supplied).difference(declared))
    if unexpected:
        raise LineMessageConfigurationError(
            "unexpected message template variables: " + ", ".join(unexpected)
        )
    normalized = {key: "" if value is None else str(value) for key, value in supplied.items()}
    content = _render_value(template["content"], normalized)
    if template["message_type"] == "text":
        payload = {"type": "text", "text": content}
        kind = LineMessageKind.TEXT
    else:
        payload = content
        if not isinstance(payload, dict):
            raise LineMessageConfigurationError("rendered Flex message must be an object")
        kind = LineMessageKind.FLEX
    return RenderedLineMessage(kind, canonical_line_payload_json(payload))


def follow_schedule_steps(
    definition: Mapping[str, object],
    templates: Mapping[str, object],
    followed_at: datetime,
) -> tuple[FollowScheduleStep, ...]:
    validate_message_schedules(definition, templates)
    if followed_at.tzinfo is None or followed_at.utcoffset() is None:
        raise LineMessageConfigurationError("followed_at must be timezone-aware")
    zone = _timezone(definition.get("timezone", "Asia/Taipei"))
    local_date = followed_at.astimezone(zone).date()
    result: list[FollowScheduleStep] = []
    for schedule in _object_list(definition, "schedules"):
        if schedule.get("enabled", True) is not True:
            continue
        schedule_id = str(schedule["id"])
        restart = schedule.get("restart_on_refollow", False) is True
        for step in _object_list(schedule, "steps"):
            send_time = _parsed_send_time(step["send_time"])
            local_scheduled = datetime.combine(
                local_date + timedelta(days=int(step["day"])),
                send_time,
                tzinfo=zone,
            )
            result.append(
                FollowScheduleStep(
                    schedule_id,
                    int(step["day"]),
                    str(step["template_id"]),
                    local_scheduled.astimezone(timezone.utc),
                    restart,
                )
            )
    return tuple(sorted(result, key=lambda item: (item.scheduled_at, item.schedule_id)))


def _render_value(value: object, variables: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return _VARIABLE.sub(lambda match: variables.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {str(key): _render_value(item, variables) for key, item in value.items()}
    return value


def _declared_variables(template: Mapping[str, object]) -> set[str]:
    return {
        _identifier(item.get("name"), "template variable")
        for item in _object_list(template, "variables", required=False)
    }


def _variables_in_value(value: object) -> set[str]:
    if isinstance(value, str):
        return set(_VARIABLE.findall(value))
    if isinstance(value, list):
        return set().union(*(_variables_in_value(item) for item in value), set())
    if isinstance(value, dict):
        return set().union(*(_variables_in_value(item) for item in value.values()), set())
    return set()


def _object_list(
    value: Mapping[str, object],
    key: str,
    *,
    required: bool = True,
) -> list[dict[str, object]]:
    raw = value.get(key)
    if raw is None and not required:
        return []
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise LineMessageConfigurationError(f"{key} must be a list of objects")
    return raw


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", value):
        raise LineMessageConfigurationError(f"{field} is invalid")
    return value


def _timezone(value: object) -> ZoneInfo:
    if not isinstance(value, str) or not value.strip():
        raise LineMessageConfigurationError("schedule timezone is invalid")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise LineMessageConfigurationError("schedule timezone is unknown") from error


def _parsed_send_time(value: object) -> time:
    match = _SEND_TIME.fullmatch(str(value))
    if match is None:
        raise LineMessageConfigurationError("schedule send_time must be HH:MM")
    return time(int(match.group("hour")), int(match.group("minute")))


__all__ = [
    "FollowScheduleStep",
    "LineMessageConfigurationError",
    "RenderedLineMessage",
    "configuration_definition",
    "follow_schedule_steps",
    "render_message_template",
    "validate_message_schedules",
    "validate_message_templates",
]

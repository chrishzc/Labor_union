"""Translate LINE postback payloads into owner-Domain commands."""

from collections.abc import Mapping

from subsystems.scheduling.matching_communication_workflow import record_matching_plan_willingness


class LinePostbackIntentError(ValueError):
    pass


def handle_matching_willingness(parameters: Mapping[str, str], event_id: str, user_id: str):
    action = parameters.get("action")
    if action not in {"willing", "unwilling"}:
        return None
    willingness = action
    return record_matching_plan_willingness(
        _text(parameters, "case_no"),
        _positive(parameters, "plan_id"),
        _positive(parameters, "segment_id"),
        willingness,
        _text({"event_id": event_id}, "event_id"),
        f"line:{_text({'user_id': user_id}, 'user_id')}",
        reply_to_user_id=user_id,
        reply_message=_reply(willingness),
    )


def _text(values: Mapping[str, str], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LinePostbackIntentError(f"LINE postback requires {field}")
    return value.strip()


def _positive(values: Mapping[str, str], field: str) -> int:
    value = _text(values, field)
    if not value.isdecimal() or int(value) <= 0:
        raise LinePostbackIntentError(f"LINE postback {field} must be positive")
    return int(value)


def _reply(willingness: str) -> str:
    if willingness == "willing":
        return "感謝您的確認！已記錄您同意此服務區段。"
    return "已記錄您的回覆，期待下次為您媒合合適的服務區段。"

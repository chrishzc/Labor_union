"""Pure Flex renderers for matching invitations and profile decisions."""

from __future__ import annotations

from typing import Mapping, Sequence

from domains.line.canonical_payload import canonical_line_payload_json
from domains.scheduling.matching_communication import MatchingNotificationKind


def caregiver_information_card(
    kind: MatchingNotificationKind,
    facts: Mapping[str, object],
    interaction_token: str,
) -> str:
    title = "服務案件資訊（一）" if kind is MatchingNotificationKind.CAREGIVER_INFO_1 else "服務案件資訊（二）"
    rows = _caregiver_fact_rows(kind, facts)
    contents = [_title(title), *(_fact_row(label, value) for label, value in rows)]
    contents.append(_notice("請確認檔期與條件後回覆是否願意承接。"))
    return canonical_line_payload_json(
        _bubble_payload(title, contents, _caregiver_actions(interaction_token))
    )


def customer_profiles_card(
    case_no: str,
    profiles: Sequence[Mapping[str, object]],
    interaction_token: str,
    note: str,
) -> str:
    bubbles = [_profile_bubble(profile) for profile in profiles]
    bubbles.append(_customer_decision_bubble(case_no, interaction_token, note))
    payload = {
        "type": "flex",
        "altText": f"案件 {case_no} 的月嫂資料與確認",
        "contents": {"type": "carousel", "contents": bubbles},
    }
    return canonical_line_payload_json(payload)


def _caregiver_fact_rows(kind, facts):
    common = (
        ("案件編號", facts.get("case_no")),
        ("服務區間", f"{facts.get('start_date')} ～ {facts.get('end_date')}"),
        ("服務縣市", facts.get("city") or "未提供"),
    )
    if kind is MatchingNotificationKind.CAREGIVER_INFO_1:
        return (*common, ("服務方式", facts.get("service_type") or "未提供"))
    return (
        *common,
        ("服務時段", facts.get("service_time") or "未提供"),
        ("寶寶資訊", facts.get("baby_info") or "未提供"),
        ("居住型態", facts.get("residence_type") or "未提供"),
    )


def _profile_bubble(profile):
    name = str(profile.get("name") or "月嫂")
    rows = (
        ("居住地", profile.get("city") or "未提供"),
        ("照護寶寶數", profile.get("care_babies") or 1),
        ("嬰幼兒按摩證書", "有" if profile.get("has_massage_cert") else "未登記"),
        ("服務區域", _list_text(profile.get("service_regions"))),
        ("技能與偏好", _list_text(profile.get("special_skills"))),
    )
    body = [_title(name), *(_fact_row(label, value) for label, value in rows)]
    return _bubble(body)


def _customer_decision_bubble(case_no, token, note):
    body = [
        _title("請確認配對方案"),
        _fact_row("案件編號", case_no),
        _notice(note),
    ]
    return _bubble(body, _customer_actions(token))


def _bubble_payload(alt_text, body, footer):
    return {
        "type": "flex",
        "altText": alt_text,
        "contents": _bubble(body, footer),
    }


def _bubble(body, footer=None):
    bubble = {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "spacing": "md", "contents": body},
    }
    if footer:
        bubble["footer"] = {"type": "box", "layout": "vertical", "spacing": "sm", "contents": footer}
    return bubble


def _title(text):
    return {"type": "text", "text": str(text), "weight": "bold", "size": "xl", "wrap": True}


def _fact_row(label, value):
    return {
        "type": "box",
        "layout": "baseline",
        "contents": [
            {"type": "text", "text": str(label), "size": "sm", "color": "#666666", "flex": 3},
            {"type": "text", "text": str(value), "size": "sm", "wrap": True, "flex": 5},
        ],
    }


def _notice(text):
    return {"type": "text", "text": str(text), "size": "sm", "wrap": True, "color": "#444444"}


def _caregiver_actions(token):
    return [
        _postback_button("願意承接", token, "willing", "#06C755"),
        _postback_button("目前無法承接", token, "unwilling", "#888888"),
    ]


def _customer_actions(token):
    return [
        _postback_button("接受此配對", token, "accepted", "#06C755"),
        _postback_button("希望先聯絡", token, "contact_requested", "#1677FF"),
        _postback_button("不接受此配對", token, "declined", "#888888"),
    ]


def _postback_button(label, token, decision, color):
    return {
        "type": "button",
        "style": "primary",
        "color": color,
        "action": {
            "type": "postback",
            "label": label,
            "data": f"matching:{token}:{decision}",
            "displayText": label,
        },
    }


def _list_text(value):
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value if item) or "未提供"
    return str(value or "未提供")


__all__ = ["caregiver_information_card", "customer_profiles_card"]

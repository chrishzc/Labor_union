"""Pure conversion from management Rich Menu JSON to LINE provider payload."""

from __future__ import annotations

import json
import os
from typing import Mapping

from domains.line.canonical_payload import canonical_line_payload_json


def rich_menu_provider_definition(definition: str | Mapping[str, object]) -> str:
    menu = json.loads(definition) if isinstance(definition, str) else dict(definition)
    size = _object(menu.get("size"), "Rich Menu size")
    width = _positive_int(size.get("width"), "Rich Menu width")
    height = _positive_int(size.get("height"), "Rich Menu height")
    buttons = menu.get("buttons")
    if not isinstance(buttons, list) or not buttons:
        raise ValueError("Rich Menu buttons must be a non-empty list")
    areas = []
    for button in buttons:
        item = _object(button, "Rich Menu button")
        bounds = _object(item.get("bounds"), "Rich Menu bounds")
        areas.append(
            {
                "bounds": {
                    "x": _positive_or_zero(bounds.get("x"), "Rich Menu bounds x"),
                    "y": _positive_or_zero(bounds.get("y"), "Rich Menu bounds y"),
                    "width": _positive_int(
                        bounds.get("width"), "Rich Menu bounds width"
                    ),
                    "height": _positive_int(
                        bounds.get("height"), "Rich Menu bounds height"
                    ),
                },
                "action": _provider_action(_object(item.get("action"), "Rich Menu action")),
            }
        )
    payload = {
        "size": {"width": width, "height": height},
        "selected": menu.get("selected", True) is True,
        "name": _text(menu.get("name"), "Rich Menu name"),
        "chatBarText": _text(menu.get("chat_bar_text"), "Rich Menu chat bar text"),
        "areas": areas,
    }
    return canonical_line_payload_json(payload)


def rich_menu_is_default(definition: str | Mapping[str, object]) -> bool:
    menu = json.loads(definition) if isinstance(definition, str) else definition
    return isinstance(menu, Mapping) and menu.get("set_as_default") is True


def _provider_action(action):
    action_type = action.get("type")
    if action_type == "message":
        return {"type": "message", "text": _text(action.get("text"), "message text")}
    if action_type == "postback":
        return {"type": "postback", "data": _text(action.get("data"), "postback data")}
    if action_type == "richmenuswitch":
        alias = _text(action.get("rich_menu_alias_id"), "rich menu alias")
        return {
            "type": "richmenuswitch",
            "richMenuAliasId": alias,
            "data": str(action.get("data") or alias).strip(),
        }
    if action_type != "uri":
        raise ValueError("Rich Menu action type is unsupported")
    if action.get("uri_source") == "liff":
        liff_id = os.getenv("LINE_LIFF_ID", "").strip()
        if not liff_id:
            raise ValueError("LINE_LIFF_ID is required for LIFF Rich Menu actions")
        suffix = str(action.get("uri") or "").strip()
        uri = f"https://liff.line.me/{liff_id}"
        if suffix.startswith("?"):
            uri += f"/{suffix}"
        elif suffix.startswith("#"):
            uri += suffix
        return {"type": "uri", "uri": uri}
    return {"type": "uri", "uri": _text(action.get("uri"), "action URI")}


def _object(value, field):
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _positive_int(value, field):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _positive_or_zero(value, field):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


__all__ = ["rich_menu_is_default", "rich_menu_provider_definition"]

"""
File: rich_menu_draft.py
Description: 驗證並正規化 Rich Menu 草稿與封閉 typed action，不接觸 provider。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import re
from typing import Any
from urllib.parse import urlparse

from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
    require_sha256_hex,
)

_ACTION_KINDS = frozenset({"uri", "message", "postback", "richmenuswitch"})
_AUDIENCE_ROLES = frozenset({"visitor", "customer", "staff", "union_staff", "union_staff_page"})
_LIFF_TARGETS = frozenset(
    {
        "?entry=gateway",
        "?entry=registration",
        "?target=ai_assistant",
        "?target=anomalies_center",
        "?target=customer_service",
        "?target=dashboard",
        "?target=faq",
        "?target=gateway",
        "?target=order_update",
        "?target=order_tracking",
        "?target=profile_update",
        "?target=staff_leave_apply",
        "?target=staff_order_search",
        "?target=staff_payout",
        "?target=staff_profile_update",
        "?target=staff_review",
        "?target=staff_schedule",
        "?target=staff_verification",
    }
)
_LIFF_TARGETS_BY_AUDIENCE = {
    "visitor": frozenset(
        {
            "?entry=gateway",
            "?entry=registration",
            "?target=ai_assistant",
            "?target=faq",
            "?target=gateway",
            "?target=staff_verification",
        }
    ),
    "customer": frozenset(
        {
            "?target=ai_assistant",
            "?target=faq",
            "?target=order_update",
            "?target=profile_update",
        }
    ),
    "staff": frozenset(
        {
            "?target=staff_leave_apply",
            "?target=staff_order_search",
            "?target=staff_payout",
            "?target=staff_profile_update",
            "?target=staff_schedule",
        }
    ),
    "union_staff": frozenset(
        {
            "?target=anomalies_center",
            "?target=customer_service",
            "?target=dashboard",
            "?target=order_tracking",
            "?target=staff_review",
        }
    ),
    "union_staff_page": frozenset(
        {
            "?target=anomalies_center",
            "?target=customer_service",
            "?target=dashboard",
            "?target=order_tracking",
            "?target=staff_review",
        }
    ),
}
_ALIAS_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class RichMenuDraftValidationError(ValueError):
    """Raised when a draft contains unsupported or ambiguous data."""


_STAFF_MENU_LABELS = {
    "?target=staff_order_search": ("我的訂單", {"我的案件", "訂單查詢"}),
    "?target=staff_schedule": ("我的排班", {"班表與請假", "排班資訊與請假"}),
    "?target=staff_profile_update": ("我的資料", {"更新個人資料"}),
    "?target=staff_payout": ("我的薪資", {"薪資明細", "薪資請款明細"}),
}


def project_saved_staff_menu(definition: dict[str, object]) -> dict[str, object]:
    """Update the standard entries in saved generated staff menus."""
    if not isinstance(definition, dict):
        return definition
    menus = definition.get("menus")
    if not isinstance(menus, list):
        return definition
    current_menus = []
    for menu in menus:
        if isinstance(menu, dict) and menu.get("audience_role") == "staff":
            buttons = menu.get("buttons")
            if isinstance(buttons, list):
                appearance = menu.get("appearance")
                generated = not isinstance(appearance, dict) or appearance.get("image_mode", "generated") == "generated"
                has_profile_button = any(
                    isinstance(button, dict) and isinstance(button.get("action"), dict)
                    and button["action"].get("uri") == "?target=staff_profile_update"
                    for button in buttons
                )
                current_buttons = []
                for button in buttons:
                    retired = _is_retired_staff_baby_log(button)
                    default_contact = (
                        generated and isinstance(button, dict) and button.get("id") == "staff_human_contact"
                        and button.get("bounds") == _staff_profile_slot()
                        and isinstance(button.get("action"), dict)
                        and button["action"].get("data") == "customer-service:handoff:confirm"
                    )
                    if not retired and not (default_contact and not has_profile_button):
                        current_buttons.append(_updated_staff_menu_label(button) if generated else button)
                    elif generated and not has_profile_button:
                        current_buttons.append(_profile_button(button))
                        has_profile_button = True
                if generated and not has_profile_button and _has_standard_profile_vacancy(menu, current_buttons):
                    current_buttons.append(_profile_button({
                        "id": "staff_profile_update", "bounds": _staff_profile_slot(),
                        "text_color": "#FFFFFF", "background_color": "#10B981", "border_radius": 54,
                    }))
                menu = {**menu, "buttons": current_buttons}
        current_menus.append(menu)
    return {**definition, "menus": current_menus}


def _staff_profile_slot() -> dict[str, int]:
    return {"x": 0, "y": 843, "width": 1250, "height": 843}


def _profile_button(button: dict) -> dict:
    return {
        **button, "label": _STAFF_MENU_LABELS["?target=staff_profile_update"][0],
        "action": {"type": "uri", "uri_source": "liff", "uri": "?target=staff_profile_update"},
    }


def _updated_staff_menu_label(button: object) -> object:
    action = button.get("action") if isinstance(button, dict) else None
    if not isinstance(action, dict) or action.get("type") != "uri" or action.get("uri_source") != "liff":
        return button
    target = action.get("uri")
    label = button.get("label")
    if isinstance(target, str) and target in _STAFF_MENU_LABELS and isinstance(label, str):
        current, previous = _STAFF_MENU_LABELS[target]
        if label in previous:
            return {**button, "label": current}
    return button


def _has_standard_profile_vacancy(menu: dict, buttons: list) -> bool:
    if menu.get("size") != {"width": 2500, "height": 1686} or len(buttons) != 3:
        return False
    expected = [
        {**_staff_profile_slot(), "x": x, "y": y}
        for x, y in ((0, 0), (1250, 0), (1250, 843))
    ]
    if any(isinstance(button, dict) and button.get("id") == "staff_profile_update" for button in buttons):
        return False
    bounds = [button.get("bounds") for button in buttons if isinstance(button, dict)]
    return all(slot in bounds for slot in expected)


def _is_retired_staff_baby_log(button: object) -> bool:
    action = button.get("action") if isinstance(button, dict) else None
    return (
        isinstance(action, dict)
        and action.get("type") == "uri"
        and action.get("uri_source") == "liff"
        and action.get("uri") == "?target=staff_baby_log"
    )


def normalize_rich_menu_draft(definition: Mapping[str, object]) -> dict[str, object]:
    """Return a canonical project-owned draft without provider-only fields."""
    root = _mapping(definition, "Rich Menu definition")
    _only_keys(root, {"version", "menus"}, "Rich Menu definition")
    version = root.get("version", 1)
    require_positive_integer(version, "Rich Menu version")
    menus_raw = _sequence(root.get("menus", []), "Rich Menu menus")
    menu_ids: set[str] = set()
    enabled_roles: set[str] = set()
    menus = []
    for index, raw_menu in enumerate(menus_raw):
        menu = _normalize_menu(raw_menu, index)
        menu_id = str(menu["id"])
        if menu_id in menu_ids:
            raise RichMenuDraftValidationError("Rich Menu IDs must be unique")
        menu_ids.add(menu_id)
        role = str(menu["audience_role"])
        if bool(menu["enabled"]) and role in {"visitor", "customer", "staff", "union_staff"}:
            if role in enabled_roles:
                raise RichMenuDraftValidationError("only one enabled menu is allowed per audience role")
            enabled_roles.add(role)
        menus.append(menu)
    _validate_menu_switch_audiences(menus)
    return {"version": version, "menus": menus}


def _validate_menu_switch_audiences(menus: Sequence[Mapping[str, object]]) -> None:
    alias_audiences = {
        str(menu["rich_menu_alias_id"]): str(menu["audience_role"])
        for menu in menus
        if menu.get("rich_menu_alias_id") is not None
    }
    for menu in menus:
        source_audience = str(menu["audience_role"])
        for button in _sequence(menu["buttons"], "Rich Menu buttons"):
            action = _mapping(_mapping(button, "Rich Menu button")["action"], "Rich Menu action")
            if action.get("type") != "richmenuswitch":
                continue
            target_alias = str(action["rich_menu_alias_id"])
            target_audience = alias_audiences.get(target_alias)
            if target_audience is None:
                raise RichMenuDraftValidationError("Rich Menu switch target alias is unknown")
            source_family = "union_staff" if source_audience == "union_staff_page" else source_audience
            target_family = "union_staff" if target_audience == "union_staff_page" else target_audience
            if source_family != target_family:
                raise RichMenuDraftValidationError(
                    "Rich Menu switch target belongs to a different audience"
                )


def normalize_rich_menu_action(action: Mapping[str, object]) -> dict[str, object]:
    value = _mapping(action, "Rich Menu action")
    _only_keys(
        value,
        {"type", "text", "displayText", "uri", "uri_source", "data", "rich_menu_alias_id"},
        "Rich Menu action",
    )
    kind = require_canonical_text(value.get("type"), "Rich Menu action type", 32)
    if kind not in _ACTION_KINDS:
        raise RichMenuDraftValidationError("Rich Menu action type is unsupported")
    supplied = {
        key: item
        for key, item in value.items()
        if key != "type" and item is not None
    }
    if kind != "uri" and supplied.get("uri_source") == "literal":
        supplied.pop("uri_source")
    if kind == "message":
        _reject_keys(supplied, {"uri", "uri_source", "data", "rich_menu_alias_id"}, kind)
        text = require_canonical_text(supplied.get("text"), "Rich Menu message text", 300)
        return {"type": kind, "text": text}
    if kind == "postback":
        _reject_keys(supplied, {"uri", "uri_source", "rich_menu_alias_id"}, kind)
        data = require_canonical_text(supplied.get("data"), "Rich Menu postback data", 300)
        result: dict[str, Any] = {"type": kind, "data": data}
        display_text = supplied.get("displayText") or supplied.get("text")
        if display_text is not None:
            result["displayText"] = require_canonical_text(
                display_text, "Rich Menu postback displayText", 300
            )
        return result
    if kind == "richmenuswitch":
        _reject_keys(supplied, {"text", "uri", "uri_source"}, kind)
        alias = require_canonical_text(
            supplied.get("rich_menu_alias_id"),
            "Rich Menu alias",
            32,
        )
        if not _ALIAS_PATTERN.fullmatch(alias):
            raise RichMenuDraftValidationError("Rich Menu alias format is invalid")
        data = require_canonical_text(
            supplied.get("data", alias),
            "Rich Menu switch data",
            300,
        )
        return {"type": kind, "rich_menu_alias_id": alias, "data": data}
    _reject_keys(supplied, {"text", "data", "rich_menu_alias_id"}, kind)
    uri_source = supplied.get("uri_source", "literal")
    if uri_source not in {"literal", "liff"}:
        raise RichMenuDraftValidationError("Rich Menu URI source is invalid")
    uri = require_canonical_text(supplied.get("uri"), "Rich Menu URI", 1_000)
    if uri_source == "liff":
        if uri not in _LIFF_TARGETS:
            raise RichMenuDraftValidationError("Rich Menu LIFF target is not canonical")
    elif urlparse(uri).scheme.lower() not in {"http", "https"}:
        raise RichMenuDraftValidationError("Rich Menu literal URI scheme is not allowed")
    return {"type": kind, "uri": uri, "uri_source": uri_source}


def _normalize_menu(raw_menu: object, index: int) -> dict[str, object]:
    path = f"Rich Menu menus[{index}]"
    menu = _mapping(raw_menu, path)
    _only_keys(
        menu,
        {
            "id", "name", "audience_role", "rich_menu_alias_id", "enabled",
            "selected", "set_as_default", "chat_bar_text", "size", "appearance", "buttons",
        },
        path,
    )
    menu_id = _identifier(menu.get("id"), f"{path} ID")
    name = require_canonical_text(menu.get("name"), f"{path} name", 300)
    audience = require_canonical_text(menu.get("audience_role"), f"{path} audience", 32)
    if audience not in _AUDIENCE_ROLES:
        raise RichMenuDraftValidationError(f"{path} audience is unsupported")
    enabled = _boolean(menu.get("enabled", True), f"{path} enabled")
    selected = _boolean(menu.get("selected", True), f"{path} selected")
    default = _boolean(menu.get("set_as_default", False), f"{path} default")
    if default and audience not in {"visitor", "customer"}:
        raise RichMenuDraftValidationError("only visitor or customer Rich Menu can be the default")
    chat_bar_text = require_canonical_text(menu.get("chat_bar_text"), f"{path} chat bar text", 14)
    size = _normalize_size(menu.get("size", {"width": 2500, "height": 843}), path)
    appearance = _normalize_appearance(menu.get("appearance", {}), path)
    buttons_raw = _sequence(menu.get("buttons"), f"{path} buttons")
    if not 1 <= len(buttons_raw) <= 20:
        raise RichMenuDraftValidationError(f"{path} must contain 1 to 20 buttons")
    buttons = [_normalize_button(item, path, size, audience) for item in buttons_raw]
    ids = [str(item["id"]) for item in buttons]
    if len(ids) != len(set(ids)):
        raise RichMenuDraftValidationError(f"{path} button IDs must be unique")
    _require_non_overlapping(buttons, path)
    normalized: dict[str, object] = {
        "id": menu_id,
        "name": name,
        "audience_role": audience,
        "enabled": enabled,
        "selected": selected,
        "set_as_default": default,
        "chat_bar_text": chat_bar_text,
        "size": size,
        "appearance": appearance,
        "buttons": buttons,
    }
    alias = menu.get("rich_menu_alias_id")
    if alias is not None:
        alias = require_canonical_text(alias, f"{path} alias", 32)
        if not _ALIAS_PATTERN.fullmatch(alias):
            raise RichMenuDraftValidationError(f"{path} alias format is invalid")
        normalized["rich_menu_alias_id"] = alias
    return normalized


def _normalize_size(raw_size: object, path: str) -> dict[str, int]:
    size = _mapping(raw_size, f"{path} size")
    _only_keys(size, {"width", "height"}, f"{path} size")
    width = size.get("width", 2500)
    height = size.get("height", 843)
    if width != 2500 or height not in {843, 1686}:
        raise RichMenuDraftValidationError(f"{path} size is unsupported")
    return {"width": 2500, "height": int(height)}


def _normalize_appearance(raw: object, path: str) -> dict[str, object]:
    appearance = _mapping(raw, f"{path} appearance")
    _only_keys(
        appearance,
        {
            "background_color",
            "image_mode",
            "image_path",
            "image_asset_id",
            "image_asset_sha256",
            "image_asset_version",
        },
        f"{path} appearance",
    )
    mode = appearance.get("image_mode", "generated")
    if mode not in {"generated", "uploaded"}:
        raise RichMenuDraftValidationError(f"{path} image mode is unsupported")
    normalized: dict[str, object] = {
        "background_color": require_canonical_text(
            appearance.get("background_color", "#F5F5F5"),
            f"{path} background color",
            32,
        ),
        "image_mode": mode,
    }
    image_path = appearance.get("image_path")
    image_asset_id = appearance.get("image_asset_id")
    image_asset_sha256 = appearance.get("image_asset_sha256")
    image_asset_version = appearance.get("image_asset_version")
    if mode == "uploaded":
        if image_path is not None:
            raise RichMenuDraftValidationError(f"{path} uploaded image forbids raw image paths")
        if any(
            value is None
            for value in (image_asset_id, image_asset_sha256, image_asset_version)
        ):
            raise RichMenuDraftValidationError(
                f"{path} uploaded image requires an exact media asset reference"
            )
        normalized["image_asset_id"] = require_positive_integer(
            image_asset_id,
            f"{path} image asset ID",
        )
        normalized["image_asset_sha256"] = require_sha256_hex(
            image_asset_sha256,
            f"{path} image asset SHA-256",
        )
        normalized["image_asset_version"] = require_sha256_hex(
            image_asset_version,
            f"{path} image asset version",
        )
    return normalized


def _normalize_button(
    raw: object,
    path: str,
    size: Mapping[str, int],
    audience: str,
) -> dict[str, object]:
    button = _mapping(raw, f"{path} button")
    _only_keys(
        button,
        {"id", "label", "text_color", "background_color", "border_radius", "bounds", "action"},
        f"{path} button",
    )
    bounds = _mapping(button.get("bounds"), f"{path} button bounds")
    _only_keys(bounds, {"x", "y", "width", "height"}, f"{path} button bounds")
    normalized_bounds = {
        "x": require_nonnegative_integer(bounds.get("x"), "Rich Menu button x"),
        "y": require_nonnegative_integer(bounds.get("y"), "Rich Menu button y"),
        "width": require_positive_integer(bounds.get("width"), "Rich Menu button width"),
        "height": require_positive_integer(bounds.get("height"), "Rich Menu button height"),
    }
    if normalized_bounds["x"] + normalized_bounds["width"] > size["width"]:
        raise RichMenuDraftValidationError("Rich Menu button exceeds menu width")
    if normalized_bounds["y"] + normalized_bounds["height"] > size["height"]:
        raise RichMenuDraftValidationError("Rich Menu button exceeds menu height")
    action = normalize_rich_menu_action(
        _mapping(button.get("action"), "Rich Menu button action")
    )
    if action["type"] == "uri" and action.get("uri_source") == "liff":
        if action["uri"] not in _LIFF_TARGETS_BY_AUDIENCE[audience]:
            raise RichMenuDraftValidationError(
                f"Rich Menu button LIFF target is not allowed for {audience} audience"
            )
    return {
        "id": _identifier(button.get("id"), "Rich Menu button ID"),
        "label": require_canonical_text(button.get("label"), "Rich Menu button label", 20),
        "text_color": require_canonical_text(button.get("text_color", "#FFFFFF"), "Rich Menu text color", 32),
        "background_color": require_canonical_text(
            button.get("background_color", "#4A90E2"),
            "Rich Menu background color",
            32,
        ),
        "border_radius": _bounded_integer(button.get("border_radius", 0), 0, 160, "Rich Menu border radius"),
        "bounds": normalized_bounds,
        "action": action,
    }


def _require_non_overlapping(buttons: Sequence[Mapping[str, object]], path: str) -> None:
    for index, button in enumerate(buttons):
        first = _mapping(button["bounds"], "Rich Menu button bounds")
        for other in buttons[index + 1:]:
            second = _mapping(other["bounds"], "Rich Menu button bounds")
            separated = (
                int(first["x"]) + int(first["width"]) <= int(second["x"])
                or int(second["x"]) + int(second["width"]) <= int(first["x"])
                or int(first["y"]) + int(first["height"]) <= int(second["y"])
                or int(second["y"]) + int(second["height"]) <= int(first["y"])
            )
            if not separated:
                raise RichMenuDraftValidationError(f"{path} buttons overlap")


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RichMenuDraftValidationError(f"{field} must be an object")
    return deepcopy(dict(value))


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RichMenuDraftValidationError(f"{field} must be an array")
    return list(value)


def _only_keys(value: Mapping[str, object], allowed: set[str], field: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise RichMenuDraftValidationError(f"{field} contains unsupported fields")


def _reject_keys(value: Mapping[str, object], forbidden: set[str], kind: str) -> None:
    if forbidden.intersection(value):
        raise RichMenuDraftValidationError(f"{kind} action contains incompatible fields")


def _identifier(value: object, field: str) -> str:
    result = require_canonical_text(value, field, 191)
    if not _IDENTIFIER_PATTERN.fullmatch(result):
        raise RichMenuDraftValidationError(f"{field} format is invalid")
    return result


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise RichMenuDraftValidationError(f"{field} must be boolean")
    return value


def _bounded_integer(value: object, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RichMenuDraftValidationError(f"{field} is outside the allowed range")
    return value


__all__ = [
    "RichMenuDraftValidationError",
    "normalize_rich_menu_action",
    "normalize_rich_menu_draft",
]

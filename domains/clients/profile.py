"""Closed validation and canonical payload rules for Client profile changes."""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Mapping


CLIENT_PROFILE_FIELDS = (
    "name", "gender", "phone", "city", "address",
    "residence_type", "delivery_type", "baby_info", "notes",
)
CLIENT_PROFILE_FIELD_SET = frozenset(CLIENT_PROFILE_FIELDS)
VALID_GENDERS = frozenset({"女", "男"})
VALID_RESIDENCE_TYPES = frozenset({"電梯大樓", "公寓", "透天", "其他"})
VALID_DELIVERY_TYPES = frozenset({"自然產", "剖腹產", "未定"})
_PHONE = re.compile(r"^09[0-9]{8}$")


class ClientProfileValidationError(ValueError):
    """Raised when a requested field is outside the closed Client contract."""

    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(code if field is None else f"{code}:{field}")


def validate_changes(
    changes: Mapping[str, object], *, city_allowlist: Collection[str] | None = None
) -> dict[str, str]:
    if not isinstance(changes, Mapping) or not changes:
        raise ClientProfileValidationError("profile_changes_required")
    normalized: dict[str, str] = {}
    for field, value in changes.items():
        if field not in CLIENT_PROFILE_FIELD_SET:
            raise ClientProfileValidationError("profile_field_not_allowed", str(field))
        if not isinstance(value, str):
            raise ClientProfileValidationError("profile_value_must_be_text", field)
        value = value.strip()
        if not value:
            raise ClientProfileValidationError("profile_value_cannot_be_empty", field)
        maximum = {
            "name": 100, "phone": 10, "city": 20, "address": 255,
            "baby_info": 255, "notes": 1000, "gender": 2,
            "residence_type": 10, "delivery_type": 10,
        }[field]
        if len(value) > maximum:
            raise ClientProfileValidationError("profile_value_too_long", field)
        if field == "gender" and value not in VALID_GENDERS:
            raise ClientProfileValidationError("profile_gender_invalid", field)
        if field == "phone" and not _PHONE.fullmatch(value):
            raise ClientProfileValidationError("profile_phone_invalid", field)
        if field == "city" and (city_allowlist is None or value not in city_allowlist):
            raise ClientProfileValidationError("profile_city_invalid", field)
        if field == "residence_type" and value not in VALID_RESIDENCE_TYPES:
            raise ClientProfileValidationError("profile_residence_type_invalid", field)
        if field == "delivery_type" and value not in VALID_DELIVERY_TYPES:
            raise ClientProfileValidationError("profile_delivery_type_invalid", field)
        normalized[field] = value
    return {key: normalized[key] for key in sorted(normalized)}


def requested_before_values(profile: Mapping[str, object], changes: Mapping[str, str]) -> dict[str, str]:
    missing = [field for field in changes if field not in profile]
    if missing:
        raise ClientProfileValidationError("profile_source_field_missing", missing[0])
    return {field: str(profile[field]) for field in sorted(changes)}

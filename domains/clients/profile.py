"""Closed validation and canonical payload rules for Client profile changes."""

from __future__ import annotations

import re
from datetime import date
from collections.abc import Collection
from typing import Mapping


CLIENT_PROFILE_FIELDS = (
    "name", "gender", "phone", "email", "city", "address",
    "residence_type", "delivery_type", "baby_info", "notes", "due_month", "reject_reason", "service_type",
)
CLIENT_PROFILE_FIELD_SET = frozenset(CLIENT_PROFILE_FIELDS)
CLIENT_PROFILE_APPLICANT_FIELDS = frozenset(
    {"name", "gender", "phone", "delivery_type", "baby_info", "notes"}
)
VALID_GENDERS = frozenset({"女", "男"})
VALID_RESIDENCE_TYPES = frozenset({"電梯大樓", "公寓", "透天", "其他"})
VALID_DELIVERY_TYPES = frozenset({"自然產", "剖腹產", "未定"})
CLIENT_PHONE_PATTERN = re.compile(r"(?:09[0-9]{8}|0[2-8][0-9]{7,8})")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_SERVICE_TYPES = frozenset({"連續服務", "休周六", "休周日", "週休2日"})


def normalize_client_phone(value: str) -> str:
    """Canonicalize a mobile or landline contact number without inventing digits."""
    text = re.sub(r"[\s()（）-]", "", value)
    if text.startswith("+886"):
        text = "0" + text[4:]
    elif text.startswith("886"):
        text = "0" + text[3:]
    return text


class ClientProfileValidationError(ValueError):
    """Raised when a requested field is outside the closed Client contract."""

    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(code if field is None else f"{code}:{field}")


def validate_changes(
    changes: Mapping[str, object],
    *,
    allowed_fields: Collection[str] | None = None,
) -> dict[str, str]:
    if not isinstance(changes, Mapping) or not changes:
        raise ClientProfileValidationError("profile_changes_required")
    normalized: dict[str, str] = {}
    effective_fields = CLIENT_PROFILE_FIELD_SET if allowed_fields is None else frozenset(allowed_fields)
    for field, value in changes.items():
        if field not in effective_fields:
            raise ClientProfileValidationError("profile_field_not_allowed", str(field))
        if not isinstance(value, str):
            raise ClientProfileValidationError("profile_value_must_be_text", field)
        value = value.strip()
        if field == "phone":
            value = normalize_client_phone(value)
        if not value:
            raise ClientProfileValidationError("profile_value_cannot_be_empty", field)
        maximum = {
            "name": 100, "phone": 10, "email": 100, "city": 20, "address": 255,
            "baby_info": 255, "notes": 1000, "gender": 2,
            "residence_type": 10, "delivery_type": 10,
            "due_month": 10, "reject_reason": 500, "service_type": 10,
        }[field]
        if len(value) > maximum:
            raise ClientProfileValidationError("profile_value_too_long", field)
        if field == "gender" and value not in VALID_GENDERS:
            raise ClientProfileValidationError("profile_gender_invalid", field)
        if field == "phone" and not CLIENT_PHONE_PATTERN.fullmatch(value):
            raise ClientProfileValidationError("profile_phone_invalid", field)
        if field == "email" and not _EMAIL.fullmatch(value):
            raise ClientProfileValidationError("profile_email_invalid", field)
        if field == "service_type" and value not in VALID_SERVICE_TYPES:
            raise ClientProfileValidationError("profile_service_type_invalid", field)
        if field == "residence_type" and value not in VALID_RESIDENCE_TYPES:
            raise ClientProfileValidationError("profile_residence_type_invalid", field)
        if field == "delivery_type" and value not in VALID_DELIVERY_TYPES:
            raise ClientProfileValidationError("profile_delivery_type_invalid", field)
        if field == "due_month":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError as error:
                raise ClientProfileValidationError("profile_due_month_invalid", field) from error
        normalized[field] = value
    return {key: normalized[key] for key in sorted(normalized)}


def requested_before_values(profile: Mapping[str, object], changes: Mapping[str, str]) -> dict[str, str]:
    missing = [field for field in changes if field not in profile]
    if missing:
        raise ClientProfileValidationError("profile_source_field_missing", missing[0])
    return {field: str(profile[field]) for field in sorted(changes)}

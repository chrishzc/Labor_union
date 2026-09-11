"""Closed validation for Staff-owned personal/contact profile changes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime


STAFF_PROFILE_FIELDS = (
    "name", "identity_card", "phone", "tel", "tel_ext", "email", "birthday",
    "city", "zip_code", "address", "education", "emergency_contact_name",
    "emergency_contact_phone", "admin_notes",
)
_MAXIMUMS = {
    "name": 100,
    "identity_card": 20,
    "phone": 20,
    "tel": 20,
    "tel_ext": 10,
    "email": 100,
    "city": 50,
    "zip_code": 10,
    "address": 255,
    "education": 255,
    "emergency_contact_name": 100,
    "emergency_contact_phone": 30,
    "admin_notes": 2000,
}
_IDENTITY_CARD = re.compile(r"^[A-Z][12][0-9]{8}$")


class StaffProfileValidationError(ValueError):
    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(code if field is None else f"{code}:{field}")


def normalize_staff_profile_changes(changes: Mapping[str, object]) -> dict[str, str | None]:
    if not isinstance(changes, Mapping) or not changes:
        raise StaffProfileValidationError("staff_profile_changes_required")
    result: dict[str, str | None] = {}
    for field, raw_value in changes.items():
        if field not in STAFF_PROFILE_FIELDS:
            raise StaffProfileValidationError("staff_profile_field_not_allowed", str(field))
        if field == "birthday":
            result[field] = _birthday(raw_value)
            continue
        if raw_value is None:
            if field in {"name", "identity_card"}:
                raise StaffProfileValidationError("staff_profile_value_cannot_be_empty", field)
            result[field] = None
            continue
        if not isinstance(raw_value, str):
            raise StaffProfileValidationError("staff_profile_value_must_be_text", field)
        value = raw_value.strip()
        if not value:
            if field in {"name", "identity_card"}:
                raise StaffProfileValidationError("staff_profile_value_cannot_be_empty", field)
            result[field] = None
            continue
        if len(value) > _MAXIMUMS[field]:
            raise StaffProfileValidationError("staff_profile_value_too_long", field)
        if field == "identity_card":
            value = value.upper()
            if not _IDENTITY_CARD.fullmatch(value):
                raise StaffProfileValidationError("staff_profile_identity_card_invalid", field)
        if field == "email" and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise StaffProfileValidationError("staff_profile_email_invalid", field)
        result[field] = value
    return {key: result[key] for key in sorted(result)}


def _birthday(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as error:
            raise StaffProfileValidationError("staff_profile_birthday_invalid", "birthday") from error
    raise StaffProfileValidationError("staff_profile_birthday_invalid", "birthday")


__all__ = ["STAFF_PROFILE_FIELDS", "StaffProfileValidationError", "normalize_staff_profile_changes"]

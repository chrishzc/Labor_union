"""Closed validation for effective Client BeClass corrections."""

from __future__ import annotations

from collections.abc import Mapping


BECLASS_CORRECTION_FIELDS = (
    "name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes",
)
_MAXIMUMS = {
    "name": 100,
    "email": 100,
    "phone": 20,
    "tel": 20,
    "ext": 10,
    "city": 50,
    "zip_code": 10,
    "address": 255,
    "admin_notes": 2000,
}


class BeClassCorrectionError(ValueError):
    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(code if field is None else f"{code}:{field}")


def normalize_beclass_changes(changes: Mapping[str, object]) -> dict[str, str | None]:
    if not isinstance(changes, Mapping) or not changes:
        raise BeClassCorrectionError("beclass_changes_required")
    normalized: dict[str, str | None] = {}
    for field, raw_value in changes.items():
        if field not in BECLASS_CORRECTION_FIELDS:
            raise BeClassCorrectionError("beclass_field_not_allowed", str(field))
        if raw_value is None:
            if field == "name":
                raise BeClassCorrectionError("beclass_value_cannot_be_empty", field)
            normalized[field] = None
            continue
        if not isinstance(raw_value, str):
            raise BeClassCorrectionError("beclass_value_must_be_text", field)
        value = raw_value.strip()
        if not value:
            if field == "name":
                raise BeClassCorrectionError("beclass_value_cannot_be_empty", field)
            normalized[field] = None
            continue
        if len(value) > _MAXIMUMS[field]:
            raise BeClassCorrectionError("beclass_value_too_long", field)
        if field == "email" and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise BeClassCorrectionError("beclass_email_invalid", field)
        normalized[field] = value
    return {key: normalized[key] for key in sorted(normalized)}


__all__ = ["BECLASS_CORRECTION_FIELDS", "BeClassCorrectionError", "normalize_beclass_changes"]

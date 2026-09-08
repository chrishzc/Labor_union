"""Bounded, read-only Staff personal and contact profile projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class StaffProfileContractError(ValueError):
    """Raised when the Staff profile source violates its typed contract."""


class StaffProfileNotFound(LookupError):
    """Raised when the requested Staff root does not exist."""


@dataclass(frozen=True, slots=True)
class StaffProfile:
    staff_id: int
    registered_at: datetime | None
    identity_card: str | None
    phone: str | None
    telephone: str | None
    telephone_extension: str | None
    email: str | None
    birthday: date | None
    city: str | None
    zip_code: str | None
    address: str | None
    education: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    admin_notes: str | None


class StaffProfileRepository(Protocol):
    def fetch(self, staff_id: int) -> Mapping[str, object] | None: ...


class StaffProfileQueryApplication:
    """Return one bounded Staff-owned profile for the authenticated admin UI."""

    def __init__(self, repository: StaffProfileRepository) -> None:
        self._repository = repository

    def query(self, staff_id: int) -> StaffProfile:
        if isinstance(staff_id, bool) or not isinstance(staff_id, int) or staff_id <= 0:
            raise ValueError("staff profile staff_id must be a positive integer")
        row = self._repository.fetch(staff_id)
        if row is None:
            raise StaffProfileNotFound(f"staff:{staff_id}")
        return _profile(row, staff_id)


def _profile(row: Mapping[str, object], staff_id: int) -> StaffProfile:
    fields = {
        "id",
        "registered_at",
        "identity_card",
        "phone",
        "tel",
        "tel_ext",
        "email",
        "birthday",
        "city",
        "zip_code",
        "address",
        "education",
        "emergency_contact_name",
        "emergency_contact_phone",
        "admin_notes",
    }
    if set(row) != fields or row.get("id") != staff_id:
        raise StaffProfileContractError("staff profile row fields or identity are invalid")
    return StaffProfile(
        staff_id=staff_id,
        registered_at=_optional_datetime(row["registered_at"], "registered_at"),
        identity_card=_optional_text(row["identity_card"], "identity_card", 20),
        phone=_optional_text(row["phone"], "phone", 20),
        telephone=_optional_text(row["tel"], "tel", 20),
        telephone_extension=_optional_text(row["tel_ext"], "tel_ext", 10),
        email=_optional_text(row["email"], "email", 100),
        birthday=_optional_date(row["birthday"], "birthday"),
        city=_optional_text(row["city"], "city", 50),
        zip_code=_optional_text(row["zip_code"], "zip_code", 10),
        address=_optional_text(row["address"], "address", 255),
        education=_optional_text(row["education"], "education", 255),
        emergency_contact_name=_optional_text(
            row["emergency_contact_name"], "emergency_contact_name", 100
        ),
        emergency_contact_phone=_optional_text(
            row["emergency_contact_phone"], "emergency_contact_phone", 30
        ),
        admin_notes=_optional_text(row["admin_notes"], "admin_notes", 2000),
    )


def _optional_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StaffProfileContractError(f"staff profile {field} is invalid")
    text = value.strip()
    if len(text) > maximum:
        raise StaffProfileContractError(f"staff profile {field} is too long")
    return text


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise StaffProfileContractError(f"staff profile {field} is invalid") from error
    raise StaffProfileContractError(f"staff profile {field} is invalid")


def _optional_datetime(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as error:
            raise StaffProfileContractError(f"staff profile {field} is invalid") from error
    raise StaffProfileContractError(f"staff profile {field} is invalid")


__all__ = [
    "StaffProfile",
    "StaffProfileContractError",
    "StaffProfileNotFound",
    "StaffProfileQueryApplication",
    "StaffProfileRepository",
]

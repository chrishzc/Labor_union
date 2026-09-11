"""Bounded, read-only Staff personal and contact profile projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


_MAX_BANK_ACCOUNTS = 20


class StaffProfileContractError(ValueError):
    """Raised when the Staff profile source violates its typed contract."""


class StaffProfileNotFound(LookupError):
    """Raised when the requested Staff root does not exist."""


@dataclass(frozen=True, slots=True)
class StaffBankAccount:
    account_id: int
    bank_code: str | None
    branch_code: str | None
    account_last4: str | None
    is_primary: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class StaffProfile:
    staff_id: int
    name: str
    profile_version: int
    bank_accounts_version: int
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
    bank_accounts: tuple[StaffBankAccount, ...]


class StaffProfileRepository(Protocol):
    def fetch(self, staff_id: int) -> Mapping[str, object] | None: ...

    def fetch_bank_accounts(self, staff_id: int) -> tuple[Mapping[str, object], ...]: ...


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
        bank_rows = self._repository.fetch_bank_accounts(staff_id)
        if len(bank_rows) > _MAX_BANK_ACCOUNTS:
            raise StaffProfileContractError("staff profile bank accounts exceed bounded maximum")
        return _profile(row, bank_rows, staff_id)


def _profile(
    row: Mapping[str, object],
    bank_rows: tuple[Mapping[str, object], ...],
    staff_id: int,
) -> StaffProfile:
    fields = {
        "id",
        "name",
        "staff_profile_version",
        "bank_accounts_version",
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
        name=_required_text(row["name"], "name", 100),
        profile_version=_non_negative_version(row["staff_profile_version"], "staff_profile_version"),
        bank_accounts_version=_non_negative_version(row["bank_accounts_version"], "bank_accounts_version"),
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
        bank_accounts=tuple(_bank_account(item) for item in bank_rows),
    )


def _bank_account(row: Mapping[str, object]) -> StaffBankAccount:
    fields = {"id", "bank_code", "branch_code", "account_last4", "is_primary", "is_active"}
    if set(row) != fields:
        raise StaffProfileContractError("staff profile bank account fields are invalid")
    account_id = row["id"]
    if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
        raise StaffProfileContractError("staff profile bank account id is invalid")
    primary = row["is_primary"]
    if isinstance(primary, bool):
        is_primary = primary
    elif isinstance(primary, int) and primary in (0, 1):
        is_primary = bool(primary)
    else:
        raise StaffProfileContractError("staff profile bank account primary flag is invalid")
    return StaffBankAccount(
        account_id=account_id,
        bank_code=_optional_text(row["bank_code"], "bank_code", 10),
        branch_code=_optional_text(row["branch_code"], "branch_code", 10),
        account_last4=_optional_last4(row["account_last4"]),
        is_primary=is_primary,
        is_active=_boolean(row["is_active"], "is_active"),
    )


def _required_text(value: object, field: str, maximum: int) -> str:
    text = _optional_text(value, field, maximum)
    if text is None:
        raise StaffProfileContractError(f"staff profile {field} is required")
    return text


def _non_negative_version(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StaffProfileContractError(f"staff profile {field} is invalid")
    return value


def _boolean(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise StaffProfileContractError(f"staff profile {field} is invalid")


def _optional_last4(value: object) -> str | None:
    text = _optional_text(value, "account_last4", 4)
    if text is not None and (len(text) != 4 or not text.isdigit()):
        raise StaffProfileContractError("staff profile account_last4 is invalid")
    return text


def _optional_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StaffProfileContractError(f"staff profile {field} is invalid")
    text = value.strip()
    if not text:
        return None
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
    "StaffBankAccount",
    "StaffProfileContractError",
    "StaffProfileNotFound",
    "StaffProfileQueryApplication",
    "StaffProfileRepository",
]

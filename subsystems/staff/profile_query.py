"""Bounded, read-only Staff personal and contact profile projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from subsystems.staff.summary_query import StaffSummaryQueryRequest
from subsystems.staff.qualification_master_query import StaffRosterServiceProfile


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
    account_no: str | None = None
    account_last4: str | None = None
    is_primary: bool = False
    is_active: bool = True


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
    union_no: str | None = None


class StaffProfileRepository(Protocol):
    def fetch(self, staff_id: int) -> Mapping[str, object] | None: ...

    def fetch_bank_accounts(self, staff_id: int) -> tuple[Mapping[str, object], ...]: ...

    def fetch_page(self, *, after_id: int | None, page_size: int, staff_id: int | None) -> tuple[Mapping[str, object], ...]: ...

    def fetch_bank_accounts_for_staff(self, staff_ids: tuple[int, ...]) -> Mapping[int, tuple[Mapping[str, object], ...]]: ...

    def fetch_service_profiles(self, staff_ids: tuple[int, ...]) -> Mapping[int, StaffRosterServiceProfile]: ...


@dataclass(frozen=True, slots=True)
class StaffRosterItem:
    id: int
    union_no: str | None
    name: str
    phone: str | None
    education: str | None
    profile: StaffProfile
    service_profile: StaffRosterServiceProfile


@dataclass(frozen=True, slots=True)
class StaffRosterPage:
    items: tuple[StaffRosterItem, ...]
    next_cursor: int | None


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

    def query_page(self, request: StaffSummaryQueryRequest) -> StaffRosterPage:
        rows = self._repository.fetch_page(after_id=request.after_id, page_size=request.page_size, staff_id=request.staff_id)
        if not isinstance(rows, tuple) or len(rows) > request.page_size + 1:
            raise StaffProfileContractError("staff roster page exceeds bounded maximum")
        selected = rows[:request.page_size]
        staff_ids = tuple(row["id"] for row in selected)
        if any(isinstance(identity, bool) or not isinstance(identity, int) or identity <= 0 for identity in staff_ids) or len(set(staff_ids)) != len(staff_ids):
            raise StaffProfileContractError("staff roster identities are invalid")
        accounts = self._repository.fetch_bank_accounts_for_staff(staff_ids) if staff_ids else {}
        try:
            service_profiles = self._repository.fetch_service_profiles(staff_ids) if staff_ids else {}
        except (ValueError, TypeError) as error:
            raise StaffProfileContractError("staff roster service profile source is invalid") from error
        if set(service_profiles) != set(staff_ids):
            raise StaffProfileContractError("staff roster service profiles do not match selected identities")
        items = []
        for row, staff_id in zip(selected, staff_ids, strict=True):
            bank_rows = accounts.get(staff_id, ())
            if len(bank_rows) > _MAX_BANK_ACCOUNTS:
                raise StaffProfileContractError("staff profile bank accounts exceed bounded maximum")
            profile = _profile(row, bank_rows, staff_id)
            items.append(StaffRosterItem(staff_id, profile.union_no, profile.name, profile.phone, profile.education, profile, service_profiles[staff_id]))
        next_cursor = staff_ids[-1] if request.staff_id is None and len(rows) > request.page_size else None
        return StaffRosterPage(tuple(items), next_cursor)


def _profile(
    row: Mapping[str, object],
    bank_rows: tuple[Mapping[str, object], ...],
    staff_id: int,
) -> StaffProfile:
    fields = {
        "id",
        "union_no",
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
        union_no=_optional_text(row["union_no"], "union_no", 50),
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
    base_fields = {"id", "bank_code", "branch_code", "account_last4", "is_primary", "is_active"}
    row_fields = set(row)
    if not (row_fields == base_fields or row_fields == base_fields | {"account_no"}):
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
    account_no = _optional_text(row.get("account_no"), "account_no", 50)
    last4 = account_no[-4:] if account_no is not None else row["account_last4"]
    return StaffBankAccount(
        account_id=account_id,
        bank_code=_optional_text(row["bank_code"], "bank_code", 10),
        branch_code=_optional_text(row["branch_code"], "branch_code", 10),
        account_no=account_no,
        account_last4=_optional_last4(last4),
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
    if text is not None and (len(text) != 4 or not text.isascii() or not text.isdigit()):
        return None
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
    "StaffRosterItem",
    "StaffRosterPage",
]

"""Strict mutation contracts for Staff Profile and Staff Bank Account owners."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StaffProfileChangeSet(_StrictModel):
    name: str | None = None
    identity_card: str | None = None
    phone: str | None = None
    tel: str | None = None
    tel_ext: str | None = None
    email: str | None = None
    birthday: date | None = None
    city: str | None = None
    zip_code: str | None = None
    address: str | None = None
    education: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    admin_notes: str | None = None


class StaffProfileMutationPreviewRequest(_StrictModel):
    changes: StaffProfileChangeSet
    expected_version: int = Field(ge=0)


class StaffProfileMutationApplyRequest(StaffProfileMutationPreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class StaffProfileMutationPreviewView(_StrictModel):
    staff_id: int = Field(gt=0)
    current_version: int = Field(ge=0)
    before: dict[str, str | None]
    after: dict[str, str | None]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffProfileMutationReceiptView(_StrictModel):
    staff_id: int = Field(gt=0)
    resulting_version: int = Field(ge=1)
    changed_fields: tuple[str, ...]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str
    replayed: bool
    readback: dict[str, str | None]


class StaffBankAccountCommandView(_StrictModel):
    operation: Literal["add", "replace", "deactivate", "set_primary"]
    account_id: int | None = Field(default=None, gt=0)
    bank_code: str | None = Field(default=None, max_length=3)
    branch_code: str | None = Field(default=None, max_length=4)
    account_no: str | None = Field(default=None, max_length=20)
    is_primary: bool | None = None
    successor_account_id: int | None = Field(default=None, gt=0)


class StaffBankAccountPreviewRequest(_StrictModel):
    command: StaffBankAccountCommandView
    expected_version: int = Field(ge=0)


class StaffBankAccountApplyRequest(StaffBankAccountPreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class SafeStaffBankAccountView(_StrictModel):
    account_id: int | None = Field(default=None, gt=0)
    bank_code: str | None = None
    branch_code: str | None = None
    account_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    is_primary: bool
    is_active: bool


class StaffBankAccountPreviewView(_StrictModel):
    staff_id: int = Field(gt=0)
    current_version: int = Field(ge=0)
    operation: Literal["add", "replace", "deactivate", "set_primary"]
    before: SafeStaffBankAccountView | None = None
    after: SafeStaffBankAccountView | None = None
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffBankAccountReceiptView(_StrictModel):
    staff_id: int = Field(gt=0)
    account_id: int = Field(gt=0)
    operation: Literal["add", "replace", "deactivate", "set_primary"]
    resulting_version: int = Field(ge=1)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str
    replayed: bool
    readback: tuple[SafeStaffBankAccountView, ...]


__all__ = [name for name in globals() if name.endswith("View") or name.endswith("Request")]

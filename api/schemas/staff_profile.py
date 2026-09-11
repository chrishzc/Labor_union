"""Strict schema for one authenticated Staff personal profile."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class StaffBankAccountView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int = Field(gt=0)
    bank_code: str | None = Field(default=None, max_length=10)
    branch_code: str | None = Field(default=None, max_length=10)
    account_last4: str | None = Field(default=None, min_length=4, max_length=4, pattern=r"^[0-9]{4}$")
    is_primary: bool
    is_active: bool


class StaffProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    profile_version: int = Field(ge=0)
    bank_accounts_version: int = Field(ge=0)
    registered_at: datetime | None = None
    identity_card: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=20)
    telephone: str | None = Field(default=None, max_length=20)
    telephone_extension: str | None = Field(default=None, max_length=10)
    email: str | None = Field(default=None, max_length=100)
    birthday: date | None = None
    city: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=10)
    address: str | None = Field(default=None, max_length=255)
    education: str | None = Field(default=None, max_length=255)
    emergency_contact_name: str | None = Field(default=None, max_length=100)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)
    admin_notes: str | None = Field(default=None, max_length=2000)
    bank_accounts: tuple[StaffBankAccountView, ...] = Field(max_length=20)


__all__ = ["StaffBankAccountView", "StaffProfileView"]

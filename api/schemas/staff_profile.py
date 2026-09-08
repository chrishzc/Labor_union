"""Strict schema for one authenticated Staff personal profile."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class StaffProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
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


__all__ = ["StaffProfileView"]

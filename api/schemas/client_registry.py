"""Strict HTTP contracts for the case-centered client registry."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.order_terms import OrderTermsQueryView


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientRegistrySummaryView(_StrictModel):
    client_id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    name: str | None = None
    phone: str | None = None
    city: str | None = None
    planned_start_date: date | None = None
    order_status: str | None = None


class ClientRegistryPageView(_StrictModel):
    items: tuple[ClientRegistrySummaryView, ...]
    next_cursor: str | None = None


class ClientProfileValuesView(_StrictModel):
    name: str | None = None
    gender: str | None = None
    phone: str | None = None
    city: str | None = None
    address: str | None = None
    residence_type: str | None = None
    delivery_type: str | None = None
    baby_info: str | None = None
    notes: str | None = None


class RegistryFieldCapabilityView(_StrictModel):
    owner: Literal["client_profile", "client_beclass", "order_terms"]
    editable: bool
    reason: str | None = None


class ClientRegistryProfileView(_StrictModel):
    client_id: int = Field(gt=0)
    version: int = Field(ge=0)
    values: ClientProfileValuesView
    field_capabilities: dict[str, RegistryFieldCapabilityView]


class ClientBeClassValuesView(_StrictModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    tel: str | None = None
    ext: str | None = None
    city: str | None = None
    zip_code: str | None = None
    address: str | None = None
    admin_notes: str | None = None


class ClientRegistryBeClassView(_StrictModel):
    status: Literal["ready", "unbound", "duplicate_binding"]
    record_id: int | None = Field(default=None, gt=0)
    version: int | None = Field(default=None, ge=0)
    values: ClientBeClassValuesView | None = None
    field_capabilities: dict[str, RegistryFieldCapabilityView]


class RegistryOrderTermsSectionView(_StrictModel):
    status: Literal["ready", "not_found", "not_ready"]
    code: str | None = None
    data: OrderTermsQueryView | None = None
    field_capabilities: dict[str, RegistryFieldCapabilityView]


class ClientRegistryDetailView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    client: ClientRegistryProfileView
    beclass: ClientRegistryBeClassView
    order_terms: RegistryOrderTermsSectionView


class ClientProfileChangeSet(_StrictModel):
    name: str | None = None
    gender: str | None = None
    phone: str | None = None
    city: str | None = None
    address: str | None = None
    residence_type: str | None = None
    delivery_type: str | None = None
    baby_info: str | None = None
    notes: str | None = None


class BeClassChangeSet(_StrictModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    tel: str | None = None
    ext: str | None = None
    city: str | None = None
    zip_code: str | None = None
    address: str | None = None
    admin_notes: str | None = None


class ClientProfileAdminPreviewRequest(_StrictModel):
    changes: ClientProfileChangeSet
    expected_version: int = Field(ge=0)


class ClientProfileAdminApplyRequest(ClientProfileAdminPreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class BeClassCorrectionPreviewRequest(_StrictModel):
    changes: BeClassChangeSet
    expected_version: int = Field(ge=0)


class BeClassCorrectionApplyRequest(BeClassCorrectionPreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class RegistryMutationPreviewView(_StrictModel):
    owner: Literal["client_profile", "client_beclass"]
    aggregate_identity: str
    current_version: int = Field(ge=0)
    before: dict[str, str | None]
    after: dict[str, str | None]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class RegistryMutationReceiptView(_StrictModel):
    owner: Literal["client_profile", "client_beclass"]
    aggregate_identity: str
    resulting_version: int = Field(ge=1)
    changed_fields: tuple[str, ...]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str
    replayed: bool
    readback: dict[str, str | None]


__all__ = [name for name in globals() if name.endswith("View") or name.endswith("Request")]

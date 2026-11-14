"""Strict HTTP views for legacy virtual-account workbook Preview and Apply."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LegacyVirtualAccountRowOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_row: int = Field(ge=2)
    case_no: str
    status: Literal["create", "existing", "transfer", "conflict", "replace_required", "ineligible_year", "missing_order"]
    related_case_nos: tuple[str, ...]


class LegacyVirtualAccountPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheet_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    import_count: int = Field(ge=0)
    existing_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    non_citizen_rows: tuple[LegacyVirtualAccountRowOutcomeView, ...] = ()


class LegacyVirtualAccountReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    existing_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    replayed_workbook: bool
    non_citizen_rows: tuple[LegacyVirtualAccountRowOutcomeView, ...] = ()

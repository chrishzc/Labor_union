"""Strict HTTP views for legacy virtual-account workbook Preview and Apply."""

from pydantic import BaseModel, ConfigDict, Field


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


class LegacyVirtualAccountReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    existing_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    replayed_workbook: bool

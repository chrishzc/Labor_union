"""
File: client_beclass_import.py
Description: 定義 Client BeClass temporary workbook 的 strict Preview 與 Apply HTTP views。
"""

from pydantic import BaseModel, ConfigDict, Field


class ClientBeClassWorkbookPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheet_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    create_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    existing_conflict_count: int = Field(ge=0)
    existing_source_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientBeClassWorkbookReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    exact_replay_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    existing_conflict_count: int = Field(ge=0)
    existing_source_count: int = Field(ge=0)
    replayed_workbook: bool

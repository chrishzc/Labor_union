"""
File: line_rich_menu_drafts.py
Description: 定義 Rich Menu 專用草稿 Query、Preview、Apply 與 receipt 公開契約。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.line_config import LineMenusConfig


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RichMenuDraftPublicationLockView(_StrictModel):
    menu_definition_id: str = Field(min_length=1, max_length=191)
    configuration_revision: int = Field(ge=0)
    state: Literal["editable", "processing", "published"]
    readonly_reason: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_reason(self):
        if self.state == "editable" and self.readonly_reason is not None:
            raise ValueError("editable Rich Menu draft cannot have a readonly reason")
        if self.state != "editable" and self.readonly_reason is None:
            raise ValueError("readonly Rich Menu draft requires a business reason")
        return self


class RichMenuDraftView(_StrictModel):
    kind: Literal["rich_menus"] = "rich_menus"
    revision: int = Field(ge=0)
    definition: LineMenusConfig
    publication_locks: tuple[RichMenuDraftPublicationLockView, ...]


class RichMenuDraftPreviewRequest(_StrictModel):
    expected_revision: int = Field(ge=0)
    definition: dict[str, Any]


class RichMenuDraftPreviewView(_StrictModel):
    before_revision: int = Field(ge=0)
    resulting_revision: int = Field(ge=1)
    normalized_definition: LineMenusConfig
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class RichMenuDraftApplyRequest(RichMenuDraftPreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class RichMenuDraftReceiptView(_StrictModel):
    outcome: Literal["created", "existing"]
    committed_revision: int = Field(ge=1)
    receipt_reference: str = Field(min_length=1, max_length=191)


class RichMenuDraftApplyView(_StrictModel):
    receipt: RichMenuDraftReceiptView
    readback: RichMenuDraftView


__all__ = [
    "RichMenuDraftApplyRequest",
    "RichMenuDraftApplyView",
    "RichMenuDraftPreviewRequest",
    "RichMenuDraftPreviewView",
    "RichMenuDraftReceiptView",
    "RichMenuDraftPublicationLockView",
    "RichMenuDraftView",
]

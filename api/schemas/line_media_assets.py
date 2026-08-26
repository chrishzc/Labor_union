"""
File: line_media_assets.py
Description: 定義 Rich Menu 受控圖片 metadata list/detail 的嚴格公開回應。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RichMenuMediaAssetView(_StrictModel):
    asset_id: StrictInt = Field(gt=0)
    menu_definition_id: StrictStr = Field(min_length=1, max_length=100)
    original_filename: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    mime_type: StrictStr = Field(min_length=1, max_length=100)
    file_size: StrictInt = Field(gt=0)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    width: StrictInt = Field(gt=0)
    height: StrictInt = Field(gt=0)
    created_at: datetime
    deleted_at: datetime | None
    selectable: StrictBool
    business_reason: StrictStr | None = Field(default=None, min_length=1, max_length=500)
    asset_version: StrictStr = Field(min_length=1, max_length=191)

    @model_validator(mode="after")
    def validate_selection_state(self) -> Self:
        if self.deleted_at is None:
            if not self.selectable or self.business_reason is not None:
                raise ValueError("active Rich Menu media selection state is inconsistent")
        elif self.selectable or self.business_reason is None:
            raise ValueError("deleted Rich Menu media selection state is inconsistent")
        return self


class RichMenuMediaAssetPageView(_StrictModel):
    items: list[RichMenuMediaAssetView]
    page: StrictInt = Field(ge=1)
    page_size: StrictInt = Field(ge=1, le=100)
    total: StrictInt = Field(ge=0)
    total_pages: StrictInt = Field(ge=1)


class RichMenuMediaAssetPageResponse(_StrictModel):
    success: Literal[True] = True
    message: Literal["Success"] = "Success"
    data: RichMenuMediaAssetPageView
    error: None = None


class RichMenuMediaAssetDetailResponse(_StrictModel):
    success: Literal[True] = True
    message: Literal["Success"] = "Success"
    data: RichMenuMediaAssetView
    error: None = None


__all__ = [
    "RichMenuMediaAssetDetailResponse",
    "RichMenuMediaAssetPageResponse",
    "RichMenuMediaAssetPageView",
    "RichMenuMediaAssetView",
]

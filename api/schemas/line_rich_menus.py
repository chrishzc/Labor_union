"""
File: line_rich_menus.py
Description: 定義 Rich Menu 零寫入發布預覽與既有發布操作的嚴格 HTTP 模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from domains.line.rich_menu import LineRichMenuPublicationStatus


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RichMenuPublishPreviewRequest(_StrictModel):
    menu_id: StrictStr = Field(
        min_length=1,
        max_length=191,
        pattern=r"^\S(?:.*\S)?$",
    )
    actor_id: StrictInt = Field(gt=0)


class RichMenuPublishPreviewResult(_StrictModel):
    preview_id: StrictInt = Field(gt=0, le=9_223_372_036_854_775_807)
    config_revision: StrictStr = Field(pattern=r"^(0|[1-9][0-9]*)$", max_length=20)
    config_fingerprint: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class RichMenuPublishPreviewResponse(_StrictModel):
    success: Literal[True] = True
    message: Literal["已確認目前版本的預覽，可再次確認後套用"] = "已確認目前版本的預覽，可再次確認後套用"
    data: RichMenuPublishPreviewResult
    error: None = None


class RichMenuPublicationView(_StrictModel):
    """公開發布投影；只允許 configuration owner 所需的非敏感欄位。"""

    id: StrictInt = Field(gt=0)
    menu_definition_id: StrictStr = Field(min_length=1, max_length=191)
    configuration_revision: StrictInt = Field(ge=0)
    status: LineRichMenuPublicationStatus = Field(strict=False)
    step_receipts: list["RichMenuPublicationStepView"] = Field(default_factory=list)


class RichMenuPublicationStepView(_StrictModel):
    """已確認步驟的安全投影，不暴露 provider ID、fingerprint 或 idempotency key。"""

    step: Literal["create", "upload", "link", "switch", "cleanup"]
    acknowledged_at: datetime


class RichMenuPublicationPageView(_StrictModel):
    """已載入範圍的發布清單，不宣稱資料庫全量。"""

    items: list[RichMenuPublicationView]
    page: StrictInt = Field(ge=1)
    page_size: StrictInt = Field(ge=1, le=100)
    total: StrictInt = Field(ge=0)
    total_pages: StrictInt = Field(ge=1)


class RichMenuPublishRequest(_StrictModel):
    preview_id: StrictInt = Field(ge=1)
    reason: StrictStr = Field(
        min_length=1,
        max_length=500,
        pattern=r"^\S(?:.*\S)?$",
    )
    idempotency_key: StrictStr = Field(
        min_length=1,
        max_length=191,
        pattern=r"^\S(?:.*\S)?$",
    )
    correlation_id: StrictStr = Field(
        min_length=1,
        max_length=191,
        pattern=r"^\S(?:.*\S)?$",
    )


class RichMenuPublicationRetryRequest(_StrictModel):
    reason: StrictStr = Field(
        min_length=1,
        max_length=500,
        pattern=r"^\S(?:.*\S)?$",
    )
    idempotency_key: StrictStr = Field(
        min_length=1,
        max_length=191,
        pattern=r"^\S(?:.*\S)?$",
    )
    correlation_id: StrictStr = Field(
        min_length=1,
        max_length=191,
        pattern=r"^\S(?:.*\S)?$",
    )


class RichMenuPublicationMutationResult(_StrictModel):
    """Mutation 的最小公開結果；provider 與 command metadata 一律不投影。"""

    id: StrictInt = Field(gt=0)
    menu_definition_id: StrictStr = Field(min_length=1, max_length=191)
    configuration_revision: StrictInt = Field(ge=0)
    status: LineRichMenuPublicationStatus = Field(strict=False)


class RichMenuPublicationQueueResponse(_StrictModel):
    success: Literal[True] = True
    message: Literal["Rich Menu 發布工作已建立"] = "Rich Menu 發布工作已建立"
    data: RichMenuPublicationMutationResult
    error: None = None


class RichMenuPublicationRetryResponse(_StrictModel):
    success: Literal[True] = True
    message: Literal["發布工作已重新排入"] = "發布工作已重新排入"
    data: RichMenuPublicationMutationResult
    error: None = None


class RichMenuImageUploadResult(_StrictModel):
    """已保存 Rich Menu 圖片的非敏感 metadata 投影。"""

    id: StrictInt = Field(gt=0)
    original_filename: StrictStr | None = Field(default=None, max_length=255)
    mime_type: StrictStr = Field(min_length=1, max_length=100)
    file_size: StrictInt = Field(gt=0)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    width: StrictInt = Field(gt=0)
    height: StrictInt = Field(gt=0)
    created_at: datetime


class RichMenuImageUploadResponse(_StrictModel):
    success: Literal[True] = True
    message: Literal["Rich Menu 圖片已安全保存"] = "Rich Menu 圖片已安全保存"
    data: RichMenuImageUploadResult
    error: None = None


__all__ = [
    "RichMenuPublicationPageView",
    "RichMenuPublicationMutationResult",
    "RichMenuPublicationQueueResponse",
    "RichMenuPublicationStepView",
    "RichMenuPublicationRetryResponse",
    "RichMenuPublicationView",
    "RichMenuPublicationRetryRequest",
    "RichMenuPublishPreviewRequest",
    "RichMenuPublishPreviewResponse",
    "RichMenuPublishPreviewResult",
    "RichMenuPublishRequest",
    "RichMenuImageUploadResponse",
    "RichMenuImageUploadResult",
]

"""
File: errors.py
Description: 定義管理端 FastAPI 邊界的嚴格 Global typed error 公開傳輸模型。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class GlobalErrorCategory(StrEnum):
    """Global 共同契約允許的封閉錯誤分類。"""

    VALIDATION = "validation"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    DOMAIN_BLOCKED = "domain_blocked"
    CONFLICT = "conflict"
    IDEMPOTENCY_MISMATCH = "idempotency_mismatch"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"


class GlobalFieldErrorView(BaseModel):
    """不含輸入值、ctx 或機密內容的欄位錯誤。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    field: StrictStr
    code: StrictStr
    message: StrictStr


class GlobalTypedErrorView(BaseModel):
    """固定八欄的 Global typed error。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    # JSON transports carry the enum as a string; the enum still rejects all
    # unknown values while the remaining primitive fields stay strict.
    category: GlobalErrorCategory = Field(strict=False)
    code: StrictStr
    message: StrictStr
    field_errors: list[GlobalFieldErrorView]
    domain_blockers: list[StrictStr]
    retryable: StrictBool
    correlation_id: StrictStr
    current_version: StrictInt | None


class GlobalTypedErrorDetailView(BaseModel):
    """保留既有 FastAPI `detail.error` wrapper。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    error: GlobalTypedErrorView


class GlobalTypedErrorResponseView(BaseModel):
    """非 2xx 管理端 JSON 回應的唯一公開 wrapper。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    detail: GlobalTypedErrorDetailView

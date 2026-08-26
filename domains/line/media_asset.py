"""
File: media_asset.py
Description: 驗證 Rich Menu 受控圖片 metadata、owner、尺寸與內容版本。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
    require_sha256_hex,
)

RICH_MENU_MEDIA_CATEGORY = "rich_menu"
RICH_MENU_MEDIA_OWNER_TYPE = "line_menu"
_RICH_MENU_DIMENSIONS = frozenset({(2500, 843), (2500, 1686)})


@dataclass(frozen=True, slots=True)
class RichMenuMediaAsset:
    asset_id: int
    menu_definition_id: str
    original_filename: str | None
    mime_type: str
    file_size: int
    sha256: str
    width: int
    height: int
    created_at: datetime
    deleted_at: datetime | None

    def __post_init__(self) -> None:
        require_positive_integer(self.asset_id, "Rich Menu media asset ID")
        require_canonical_text(
            self.menu_definition_id,
            "Rich Menu media owner ID",
            100,
        )
        if self.original_filename is not None:
            require_canonical_text(
                self.original_filename,
                "Rich Menu media original filename",
                255,
            )
        mime_type = require_canonical_text(
            self.mime_type,
            "Rich Menu media MIME type",
            100,
        )
        if mime_type != mime_type.lower() or not mime_type.startswith("image/"):
            raise ValueError("Rich Menu media MIME type must be a lowercase image type")
        require_positive_integer(self.file_size, "Rich Menu media file size")
        require_sha256_hex(self.sha256, "Rich Menu media SHA-256")
        require_positive_integer(self.width, "Rich Menu media width")
        require_positive_integer(self.height, "Rich Menu media height")
        if (self.width, self.height) not in _RICH_MENU_DIMENSIONS:
            raise ValueError("Rich Menu media dimensions are unsupported")
        _require_aware_datetime(self.created_at, "Rich Menu media created_at")
        if self.deleted_at is not None:
            _require_aware_datetime(self.deleted_at, "Rich Menu media deleted_at")
            if self.deleted_at < self.created_at:
                raise ValueError("Rich Menu media deleted_at precedes created_at")

    @property
    def selectable(self) -> bool:
        return self.deleted_at is None

    @property
    def business_reason(self) -> str | None:
        if self.deleted_at is not None:
            return "此背景圖已刪除，只保留歷史查詢，不能再選用。"
        return None

    @property
    def asset_version(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "asset_id": self.asset_id,
                "owner": {
                    "category": RICH_MENU_MEDIA_CATEGORY,
                    "owner_type": RICH_MENU_MEDIA_OWNER_TYPE,
                    "owner_id": self.menu_definition_id,
                },
                "original_filename": self.original_filename,
                "mime_type": self.mime_type,
                "file_size": self.file_size,
                "sha256": self.sha256,
                "dimensions": {"width": self.width, "height": self.height},
                "created_at": self.created_at.isoformat(),
                "deleted_at": (
                    self.deleted_at.isoformat() if self.deleted_at is not None else None
                ),
            }
        )


def _require_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError(f"{field_name} must have a UTC offset")
    return value


__all__ = [
    "RICH_MENU_MEDIA_CATEGORY",
    "RICH_MENU_MEDIA_OWNER_TYPE",
    "RichMenuMediaAsset",
]

"""
File: media_asset_contracts.py
Description: 定義 Rich Menu 圖片 metadata 的 owner-scoped 唯讀查詢契約。
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from domains.line.media_asset import RichMenuMediaAsset
from shared_kernel.validation import require_canonical_text, require_positive_integer, require_sha256_hex


@dataclass(frozen=True, slots=True)
class RichMenuControlledFileReference:
    """Exact media owner FK evidence, independent of filenames/storage paths."""
    asset_id: int
    menu_definition_id: str
    file_id: str
    version: int
    sha256_digest: str
    size_bytes: int
    mime_type: str
    selectable: bool

    def __post_init__(self):
        require_positive_integer(self.asset_id, "Rich Menu asset ID")
        require_canonical_text(self.menu_definition_id, "Rich Menu owner", 100)
        if not re.fullmatch(r"cf_[0-9a-f]{32}", self.file_id):
            raise ValueError("Rich Menu controlled file identity is invalid")
        require_positive_integer(self.version, "Rich Menu controlled file version")
        require_positive_integer(self.size_bytes, "Rich Menu controlled file size")
        require_sha256_hex(self.sha256_digest, "Rich Menu controlled file SHA-256")
        if self.mime_type != "image/png" or type(self.selectable) is not bool:
            raise ValueError("Rich Menu controlled file policy is invalid")


@dataclass(frozen=True, slots=True)
class RichMenuMediaAssetListQuery:
    menu_definition_id: str
    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        require_canonical_text(
            self.menu_definition_id,
            "Rich Menu media owner ID",
            100,
        )
        require_positive_integer(self.page, "Rich Menu media page")
        require_positive_integer(self.page_size, "Rich Menu media page size")
        if self.page_size > 100:
            raise ValueError("Rich Menu media page size exceeds maximum")


@dataclass(frozen=True, slots=True)
class RichMenuMediaAssetDetailQuery:
    menu_definition_id: str
    asset_id: int

    def __post_init__(self) -> None:
        require_canonical_text(
            self.menu_definition_id,
            "Rich Menu media owner ID",
            100,
        )
        require_positive_integer(self.asset_id, "Rich Menu media asset ID")


@dataclass(frozen=True, slots=True)
class RichMenuMediaAssetPage:
    items: tuple[RichMenuMediaAsset, ...]
    page: int
    page_size: int
    total: int
    total_pages: int

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, RichMenuMediaAsset) for item in self.items
        ):
            raise TypeError("Rich Menu media page items are invalid")
        require_positive_integer(self.page, "Rich Menu media page")
        require_positive_integer(self.page_size, "Rich Menu media page size")
        if isinstance(self.total, bool) or not isinstance(self.total, int) or self.total < 0:
            raise ValueError("Rich Menu media total must be nonnegative")
        require_positive_integer(self.total_pages, "Rich Menu media total pages")
        if len(self.items) > self.page_size:
            raise ValueError("Rich Menu media page exceeds requested size")


__all__ = [
    "RichMenuMediaAssetDetailQuery",
    "RichMenuMediaAssetListQuery",
    "RichMenuMediaAssetPage",
]

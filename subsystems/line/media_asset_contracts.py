"""
File: media_asset_contracts.py
Description: 定義 Rich Menu 圖片 metadata 的 owner-scoped 唯讀查詢契約。
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.line.media_asset import RichMenuMediaAsset
from shared_kernel.validation import require_canonical_text, require_positive_integer


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

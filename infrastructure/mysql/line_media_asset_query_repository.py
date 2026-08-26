"""
File: line_media_asset_query_repository.py
Description: 唯讀查詢 Rich Menu owner-scoped 圖片 metadata，不公開儲存位置。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from domains.line.media_asset import (
    RICH_MENU_MEDIA_CATEGORY,
    RICH_MENU_MEDIA_OWNER_TYPE,
    RichMenuMediaAsset,
)
from infrastructure.mysql.line_repository_support import aware_utc, optional_row
from shared_kernel.validation import require_nonnegative_integer
from subsystems.line.media_asset_contracts import (
    RichMenuMediaAssetDetailQuery,
    RichMenuMediaAssetListQuery,
    RichMenuMediaAssetPage,
)

_PUBLIC_COLUMNS = (
    "id,category,owner_type,owner_id,original_filename,mime_type,file_size,"
    "sha256,width,height,created_at,deleted_at"
)
_OWNER_PREDICATE = "category=%s AND owner_type=%s AND owner_id=%s"
_COUNT_SQL = f"SELECT COUNT(*) AS total FROM media_assets WHERE {_OWNER_PREDICATE}"
_LIST_SQL = (
    f"SELECT {_PUBLIC_COLUMNS} FROM media_assets WHERE {_OWNER_PREDICATE} "
    "ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s"
)
_DETAIL_SQL = (
    f"SELECT {_PUBLIC_COLUMNS} FROM media_assets WHERE id=%s AND {_OWNER_PREDICATE}"
)
_DETAIL_LOCK_SQL = f"{_DETAIL_SQL} FOR UPDATE"


class MySqlLineRichMenuMediaAssetQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list(self, query: RichMenuMediaAssetListQuery) -> RichMenuMediaAssetPage:
        if not isinstance(query, RichMenuMediaAssetListQuery):
            raise TypeError("Rich Menu media list query is invalid")
        owner_parameters = (
            RICH_MENU_MEDIA_CATEGORY,
            RICH_MENU_MEDIA_OWNER_TYPE,
            query.menu_definition_id,
        )
        offset = (query.page - 1) * query.page_size
        with self._connection.cursor() as cursor:
            cursor.execute(_COUNT_SQL, owner_parameters)
            count_row = optional_row(cursor.fetchone())
            if count_row is None:
                raise RuntimeError("line_rich_menu_media_total_missing")
            total = count_row.get("total")
            require_nonnegative_integer(total, "Rich Menu media total")
            cursor.execute(
                _LIST_SQL,
                (*owner_parameters, query.page_size, offset),
            )
            rows = tuple(cursor.fetchall() or ())
        items = tuple(_asset(row, query.menu_definition_id) for row in rows)
        return RichMenuMediaAssetPage(
            items=items,
            page=query.page,
            page_size=query.page_size,
            total=total,
            total_pages=max(1, (total + query.page_size - 1) // query.page_size),
        )

    def get(
        self,
        query: RichMenuMediaAssetDetailQuery,
    ) -> RichMenuMediaAsset | None:
        return self._get(query, for_update=False)

    def get_for_update(
        self,
        query: RichMenuMediaAssetDetailQuery,
    ) -> RichMenuMediaAsset | None:
        return self._get(query, for_update=True)

    def _get(
        self,
        query: RichMenuMediaAssetDetailQuery,
        *,
        for_update: bool,
    ) -> RichMenuMediaAsset | None:
        if not isinstance(query, RichMenuMediaAssetDetailQuery):
            raise TypeError("Rich Menu media detail query is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _DETAIL_LOCK_SQL if for_update else _DETAIL_SQL,
                (
                    query.asset_id,
                    RICH_MENU_MEDIA_CATEGORY,
                    RICH_MENU_MEDIA_OWNER_TYPE,
                    query.menu_definition_id,
                ),
            )
            row = optional_row(cursor.fetchone())
        return None if row is None else _asset(row, query.menu_definition_id)


def _asset(row: Mapping[str, object], expected_menu_definition_id: str) -> RichMenuMediaAsset:
    if row.get("category") != RICH_MENU_MEDIA_CATEGORY:
        raise ValueError("Rich Menu media category drift")
    if row.get("owner_type") != RICH_MENU_MEDIA_OWNER_TYPE:
        raise ValueError("Rich Menu media owner type drift")
    if row.get("owner_id") != expected_menu_definition_id:
        raise ValueError("Rich Menu media owner ID drift")
    return RichMenuMediaAsset(
        asset_id=row.get("id"),
        menu_definition_id=expected_menu_definition_id,
        original_filename=_optional_text(row.get("original_filename")),
        mime_type=row.get("mime_type"),
        file_size=row.get("file_size"),
        sha256=row.get("sha256"),
        width=row.get("width"),
        height=row.get("height"),
        created_at=_aware_timestamp(row.get("created_at"), "created_at"),
        deleted_at=_optional_aware_timestamp(row.get("deleted_at")),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else value


def _aware_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"Rich Menu media {field_name} is invalid")
    return aware_utc(value)


def _optional_aware_timestamp(value: object) -> datetime | None:
    return None if value is None else _aware_timestamp(value, "deleted_at")


__all__ = ["MySqlLineRichMenuMediaAssetQueryRepository"]

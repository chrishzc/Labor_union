"""
File: line_media_asset_query_repository.py
Description: Rich Menu 圖片 metadata、borrowed controlled-file FK 寫入與唯讀引用，不公開儲存位置。
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
    RichMenuControlledFileReference,
)
from subsystems.controlled_files.workflow import ControlledFileReadback

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

    def find_generated_asset(self, identity, menu_id, *, for_update=False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT asset.*,object.opaque_object_id controlled_file_id FROM media_assets asset "
                "JOIN controlled_file_objects object ON object.id=asset.controlled_file_object_id "
                "WHERE asset.category='rich_menu' AND asset.owner_type='line_menu' AND asset.owner_id=%s "
                "AND object.owner_type='line_integration' AND object.purpose='rich_menu_background' "
                "AND object.subject_reference=%s AND object.object_key=%s ORDER BY asset.id LIMIT 2"
                + (" FOR UPDATE" if for_update else ""), (menu_id, menu_id, "asset:" + identity),
            )
            rows = tuple(cursor.fetchall())
        if len(rows) > 1:
            raise ValueError("line_rich_menu_generated_identity_ambiguous")
        return rows[0] if rows else None

    def register_controlled_asset(self, readback: ControlledFileReadback, *, menu_id: str, width: int, height: int,
                                  created_by_admin_user_id: int | None, storage_provider: str) -> Mapping[str, object]:
        """Borrow the caller's transaction after ControlledFile Apply, without commit."""
        from subsystems.controlled_files.workflow import ControlledFileOwner, ControlledFilePurpose
        if (readback.owner is not ControlledFileOwner.LINE_INTEGRATION
            or readback.purpose is not ControlledFilePurpose.RICH_MENU_BACKGROUND
            or readback.subject_reference != menu_id or readback.mime_type != "image/png"):
            raise ValueError("line_rich_menu_controlled_file_identity_mismatch")
        if storage_provider not in {"local", "nas"}:
            raise ValueError("line_rich_menu_storage_provider_invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT asset.* FROM media_assets asset JOIN controlled_file_objects object "
                "ON object.id=asset.controlled_file_object_id WHERE object.opaque_object_id=%s FOR UPDATE",
                (readback.file_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                if (row["category"] != "rich_menu" or row["owner_type"] != "line_menu"
                    or row["owner_id"] != menu_id or row["sha256"] != readback.sha256_digest
                    or row["file_size"] != readback.size_bytes or row["mime_type"] != readback.mime_type
                    or row["storage_key"] != readback.file_id or row["deleted_at"] is not None
                    or row["width"] != width or row["height"] != height or row["original_filename"] != readback.filename):
                    raise ValueError("line_rich_menu_controlled_file_replay_mismatch")
                return row
            cursor.execute(
                "INSERT INTO media_assets (category,owner_type,owner_id,storage_provider,storage_key,"
                "original_filename,mime_type,file_size,sha256,width,height,created_by_admin_user_id,controlled_file_object_id) "
                "SELECT 'rich_menu','line_menu',%s,%s,object.opaque_object_id,%s,'image/png',%s,%s,%s,%s,%s,object.id "
                "FROM controlled_file_objects object WHERE object.opaque_object_id=%s "
                "AND object.owner_type='line_integration' AND object.purpose='rich_menu_background' "
                "AND object.subject_reference=%s AND object.version_number=%s AND object.content_sha256=%s "
                "AND object.content_type='image/png' AND object.size_bytes=%s",
                (menu_id, storage_provider, readback.filename, readback.size_bytes, readback.sha256_digest, width, height,
                 created_by_admin_user_id, readback.file_id, menu_id, readback.version, readback.sha256_digest, readback.size_bytes),
            )
            if cursor.rowcount != 1:
                raise ValueError("line_rich_menu_controlled_file_binding_failed")
            cursor.execute("SELECT * FROM media_assets WHERE id=%s", (int(cursor.lastrowid),))
            return cursor.fetchone()

    def get_controlled_file_reference(self, file_id: str) -> RichMenuControlledFileReference | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT asset.id,asset.owner_id,asset.storage_key,asset.sha256,asset.file_size,asset.mime_type,asset.deleted_at,"
                "object.opaque_object_id,object.version_number,object.content_sha256,object.size_bytes,object.content_type,"
                "object.subject_reference FROM media_assets asset JOIN controlled_file_objects object "
                "ON object.id=asset.controlled_file_object_id WHERE object.opaque_object_id=%s "
                "AND asset.category='rich_menu' AND asset.owner_type='line_menu' "
                "AND object.owner_type='line_integration' AND object.purpose='rich_menu_background' ORDER BY asset.id LIMIT 2",
                (file_id,),
            )
            rows = tuple(cursor.fetchall())
        return _controlled_file_reference(rows[0]) if len(rows) == 1 else None

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


def _controlled_file_reference(row):
    if (row["owner_id"] != row["subject_reference"] or row["storage_key"] != row["opaque_object_id"]
        or row["sha256"] != row["content_sha256"] or row["file_size"] != row["size_bytes"]
        or row["mime_type"] != row["content_type"] or row["mime_type"] != "image/png"):
        return None
    return RichMenuControlledFileReference(int(row["id"]), str(row["owner_id"]), str(row["opaque_object_id"]),
        int(row["version_number"]), str(row["content_sha256"]), int(row["size_bytes"]), str(row["content_type"]), row["deleted_at"] is None)


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

"""Shared deployment storage root and the fixed NAS directory layout (§13B)."""
from __future__ import annotations

import os
import re
from pathlib import Path

ORDERS_DIRECTORY = "01_案件合約 (orders)"
SCHEDULING_DIRECTORY = "02_照護日誌 (scheduling)"
STAFF_DIRECTORY = "03_月嫂檔案與資格 (staff)"
MEDIA_DIRECTORY = "04_LINE選單資源 (media)"
DATABASE_BACKUP_DIRECTORY = "05_資料庫冷備份 (db_backups)"
STAGING_DIRECTORY = "_staging"
BUSINESS_DIRECTORIES = (ORDERS_DIRECTORY, SCHEDULING_DIRECTORY, STAFF_DIRECTORY, MEDIA_DIRECTORY, DATABASE_BACKUP_DIRECTORY)


class StorageLayoutError(RuntimeError):
    pass


def configured_storage_root() -> Path | None:
    value = os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip()
    root = Path(value) if value else None
    if root is not None and not is_development_environment() and not root.is_absolute():
        raise StorageLayoutError("正式 NAS 根目錄須使用完整絕對路徑；未改存本機。")
    return root


def is_development_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in {"development", "dev", "test", "testing"}


def unified_storage_enabled() -> bool:
    return configured_storage_root() is not None and not is_development_environment()


def safe_filename_component(value: str) -> str:
    if value is None:
        raise StorageLayoutError("檔案分類識別尚未完整，無法建立資料夾。")
    result = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(value)).strip(" .")
    if not result or result in {".", ".."}:
        raise StorageLayoutError("檔案分類識別無法形成安全的資料夾名稱。")
    return result


def component_storage_root(directory: str, *, legacy_variable: str, development_default: Path) -> Path:
    """Production has one root; retain explicit development roots without migration."""
    root = configured_storage_root()
    development = is_development_environment()
    legacy = os.getenv(legacy_variable, "").strip()
    if development and legacy:
        return Path(legacy)
    if root is not None:
        return root / directory
    if development:
        return development_default
    raise StorageLayoutError("尚未設定 NAS 根目錄 CONTROLLED_FILE_STORAGE_ROOT；未改存本機。")


def ensure_storage_layout(root: Path) -> None:
    """Only create children of an existing, non-linked deployment root."""
    try:
        if not root.is_dir() or root.is_symlink() or root.is_junction():
            raise StorageLayoutError("NAS 根目錄無法使用，請確認連線與權限；不會自動建立根目錄。")
        for name in (*BUSINESS_DIRECTORIES, STAGING_DIRECTORY):
            child = root / name
            if child.is_symlink() or child.is_junction():
                raise StorageLayoutError("NAS 子資料夾不能是符號連結或轉接點。")
            child.mkdir(exist_ok=True)
        menus = root / MEDIA_DIRECTORY / "rich_menus"
        if menus.is_symlink() or menus.is_junction():
            raise StorageLayoutError("NAS 子資料夾不能是符號連結或轉接點。")
        menus.mkdir(exist_ok=True)
    except OSError:
        raise StorageLayoutError("NAS 子資料夾無法建立，請確認連線與新增資料夾權限；未改存本機。") from None


def prepare_component_write(root: Path) -> None:
    """Prepare fixed shared-root components; injected development stores stay local."""
    if root.name in BUSINESS_DIRECTORIES:
        ensure_storage_layout(root.parent)
    elif root.name == "line_media" and root.parent.name == STAGING_DIRECTORY:
        ensure_storage_layout(root.parent.parent)
        if root.is_symlink() or root.is_junction():
            raise StorageLayoutError("NAS 子資料夾不能是符號連結或轉接點。")
        root.mkdir(exist_ok=True)
    else:
        # Existing explicit development/test stores keep their original locations.
        root.mkdir(parents=True, exist_ok=True)

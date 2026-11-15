"""
File: rich_menu_backup.py
Description: LINE 圖文選單 ID 之本機靜態快照原子備份與容災讀取。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IDS_BACKUP_PATH = PROJECT_ROOT / "config" / "rich_menu_ids.json"

_ROLE_TO_KEY = {
    "visitor": "default_rich_menu_id",
    "customer": "customer_rich_menu_id",
    "staff": "staff_rich_menu_id",
    "union_staff": "union_staff_rich_menu_id",
}

_DEFINITION_ID_TO_KEY = {
    "default_menu": "default_rich_menu_id",
    "customer_menu": "customer_rich_menu_id",
    "staff_menu": "staff_rich_menu_id",
    "union_staff_menu": "union_staff_rich_menu_id",
}


def write_rich_menu_id_backup(
    audience_role: str,
    rich_menu_id: str,
    *,
    path: Path | None = None,
) -> None:
    """原子更新本機 rich_menu_ids.json 快照備份，防止 DB 重置或災後復原時 ID 遺失。"""
    key = _ROLE_TO_KEY.get(audience_role) or _DEFINITION_ID_TO_KEY.get(audience_role)
    if not key or not rich_menu_id:
        return
    target_path = path or DEFAULT_IDS_BACKUP_PATH
    try:
        existing = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = {}
    if existing.get(key) == rich_menu_id:
        return
    existing[key] = rich_menu_id
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".rich-menu-ids-", suffix=".tmp", dir=target_path.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(existing, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target_path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_rich_menu_id_backup(
    menu_definition_id_or_role: str,
    *,
    path: Path | None = None,
) -> str | None:
    """從本機 rich_menu_ids.json 快照讀取備份 ID，作為 DB 查無紀錄時之容災 fallback。"""
    key = _DEFINITION_ID_TO_KEY.get(menu_definition_id_or_role) or _ROLE_TO_KEY.get(
        menu_definition_id_or_role
    )
    if not key:
        return None
    target_path = path or DEFAULT_IDS_BACKUP_PATH
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        val = str(data.get(key) or "").strip()
        if not val and key == "customer_rich_menu_id":
            val = str(data.get("default_rich_menu_id") or "").strip()
        return val or None
    except (OSError, ValueError):
        return None


__all__ = [
    "DEFAULT_IDS_BACKUP_PATH",
    "read_rich_menu_id_backup",
    "write_rich_menu_id_backup",
]

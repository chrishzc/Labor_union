"""
================================================================================
檔案名稱: line/setup_rich_menus.py
功能說明: LINE 下方選單發布命令入口，沿用可靠發布服務建立、上傳及套用 Rich Menu
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas.line_config import LineMenusConfig
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.line.configuration_store import read_config
from subsystems.line.rich_menu_publication_workflow import (
    RichMenuPublicationConflictError,
    build_line_action,
    build_line_menu,
    create_publication_preview,
    create_publication_job,
    get_publication,
    process_due_publications,
)
from subsystems.line.media_archive import render_rich_menu_image


def create_rich_menu_image(menu: dict, output_path) -> None:
    """Keep the legacy helper name while using the hardened renderer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_rich_menu_image(menu))


def main() -> None:
    config = read_config("line_menus", LineMenusConfig)
    admin_user_id = _ensure_cli_admin_user()
    publication_ids: list[int] = []
    for menu in config.menus:
        if not menu.enabled:
            continue
        try:
            preview = create_publication_preview(menu.id, admin_user_id)
            publication = create_publication_job(
                menu.id,
                admin_user_id,
                preview_id=int(preview["preview_id"]),
            )
        except RichMenuPublicationConflictError as exc:
            print(f"[Rich Menu] Skip {menu.id}: {exc}")
            continue
        publication_ids.append(int(publication["id"]))

    process_due_publications()
    for publication_id in publication_ids:
        item = get_publication(publication_id)
        print(
            f"[Rich Menu] {item['menu_config_id']}: {item['status']} "
            f"{item.get('line_rich_menu_id') or item.get('error_code') or ''}"
        )


def _ensure_cli_admin_user() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM admin_users WHERE username=%s",
                ("system:rich-menu-cli",),
            )
            row = cursor.fetchone()
            if row:
                return int(row["id"])
            cursor.execute(
                """
                INSERT INTO admin_users (
                    username, password_hash, display_name, role, enabled
                ) VALUES (%s,%s,%s,%s,1)
                """,
                (
                    "system:rich-menu-cli",
                    "local-cli-no-login",
                    "本機 Rich Menu 發布",
                    "system_admin",
                ),
            )
            admin_user_id = int(cursor.lastrowid)
        conn.commit()
        return admin_user_id
    finally:
        conn.close()


if __name__ == "__main__":
    main()

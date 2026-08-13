"""
File: setup_rich_menus.py
Description: 保留舊 Rich Menu CLI 名稱並拒絕檔案設定旁路發布。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from subsystems.line.media_archive import render_rich_menu_image


def create_rich_menu_image(menu: dict, output_path) -> None:
    """Keep the legacy helper name while using the hardened renderer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_rich_menu_image(menu))


def main() -> None:
    raise SystemExit(
        "This legacy CLI is retired. Use the authenticated Rich Menu preview and Apply flow."
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

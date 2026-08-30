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

from infrastructure.line.rich_menu_image_store import render_rich_menu_image


def create_rich_menu_image(menu: dict, output_path) -> None:
    """Keep the legacy helper name while using the hardened renderer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_rich_menu_image(menu))


def main() -> None:
    raise SystemExit(
        "This legacy CLI is retired. Use the authenticated Rich Menu preview and Apply flow."
    )


if __name__ == "__main__":
    main()

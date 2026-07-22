"""CLI compatibility wrapper for the durable Rich Menu publisher."""

from __future__ import annotations

from api.schemas.line_config import LineMenusConfig
from services.json_config_service import read_config
from services.line_rich_menu_service import (
    RichMenuPublicationConflictError,
    build_line_action,
    build_line_menu,
    create_publication_job,
    get_publication,
    process_due_publications,
)
from services.media_storage_service import render_rich_menu_image


def create_rich_menu_image(menu: dict, output_path) -> None:
    """Keep the legacy helper name while using the hardened renderer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_rich_menu_image(menu))


def main() -> None:
    config = read_config("line_menus", LineMenusConfig)
    publication_ids: list[int] = []
    for menu in config.menus:
        if not menu.enabled:
            continue
        try:
            publication = create_publication_job(menu.id, None)
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


if __name__ == "__main__":
    main()

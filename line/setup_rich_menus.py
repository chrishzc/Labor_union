"""Generate and publish LINE Rich Menus from config/line_menu.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "line_menu.json"
IDS_PATH = PROJECT_ROOT / "config" / "rich_menu_ids.json"
LINE_DIR = Path(__file__).resolve().parent

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LIFF_ID = os.getenv("LINE_LIFF_ID")


def _headers(content_type: str = "application/json") -> dict[str, str]:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": content_type,
    }


def _font(size: int = 86):
    try:
        return ImageFont.truetype("msjh.ttc", size)
    except OSError:
        return ImageFont.load_default()


def create_rich_menu_image(menu: dict, output_path: Path) -> None:
    size = menu["size"]
    appearance = menu["appearance"]
    image = Image.new(
        "RGB",
        (size["width"], size["height"]),
        color=appearance.get("background_color", "#F5F5F5"),
    )
    draw = ImageDraw.Draw(image)
    font = _font()

    for button in menu["buttons"]:
        bounds = button["bounds"]
        left = bounds["x"]
        top = bounds["y"]
        right = left + bounds["width"]
        bottom = top + bounds["height"]
        draw.rectangle(
            [left, top, right, bottom],
            fill=button.get("background_color", "#4A90E2"),
            outline="#FFFFFF",
            width=4,
        )
        label = button["label"]
        text_box = draw.textbbox((0, 0), label, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        draw.text(
            (
                left + (bounds["width"] - text_width) / 2,
                top + (bounds["height"] - text_height) / 2,
            ),
            label,
            fill=button.get("text_color", "#FFFFFF"),
            font=font,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="JPEG", quality=92)


def build_line_action(action: dict) -> dict:
    action_type = action["type"]
    if action_type == "message":
        return {"type": "message", "text": action["text"]}
    if action_type == "postback":
        return {"type": "postback", "data": action["data"]}
    if action.get("uri_source") == "liff":
        if not LIFF_ID:
            raise RuntimeError("LINE_LIFF_ID is required by a LIFF menu action")
        return {"type": "uri", "uri": f"https://liff.line.me/{LIFF_ID}"}
    return {"type": "uri", "uri": action["uri"]}


def build_line_menu(menu: dict) -> dict:
    return {
        "size": menu["size"],
        "selected": menu.get("selected", True),
        "name": menu["name"],
        "chatBarText": menu["chat_bar_text"],
        "areas": [
            {
                "bounds": button["bounds"],
                "action": build_line_action(button["action"]),
            }
            for button in menu["buttons"]
        ],
    }


def create_and_upload_rich_menu(menu: dict, image_path: Path) -> str:
    response = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=_headers(),
        json=build_line_menu(menu),
        timeout=15,
    )
    response.raise_for_status()
    menu_id = response.json()["richMenuId"]

    with image_path.open("rb") as image_stream:
        upload = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers=_headers("image/jpeg"),
            data=image_stream,
            timeout=30,
        )
    upload.raise_for_status()
    return menu_id


def main() -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        config = json.load(stream)

    rich_menu_ids: dict[str, str] = {}
    for menu in config.get("menus", []):
        if not menu.get("enabled", True):
            continue

        appearance = menu.get("appearance", {})
        configured_path = appearance.get("image_path")
        image_path = PROJECT_ROOT / configured_path if configured_path else LINE_DIR / f"{menu['id']}.jpg"

        if appearance.get("image_mode", "generated") == "generated":
            create_rich_menu_image(menu, image_path)
        elif not image_path.exists():
            raise FileNotFoundError(f"Rich menu image not found: {image_path}")

        menu_id = create_and_upload_rich_menu(menu, image_path)
        id_key = menu["id"][:-5] if menu["id"].endswith("_menu") else menu["id"]
        rich_menu_ids[f"{id_key}_rich_menu_id"] = menu_id

        if menu.get("set_as_default"):
            response = requests.post(
                f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}",
                headers=_headers(),
                timeout=15,
            )
            response.raise_for_status()

    with IDS_PATH.open("w", encoding="utf-8") as stream:
        json.dump(rich_menu_ids, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"Published {len(rich_menu_ids)} Rich Menu(s)")


if __name__ == "__main__":
    main()

"""
File: rich_menu_image_store.py
Description: LINE Rich Menu 圖片檔案儲存管理與現代化卡片圖文選單繪製渲染引擎。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_LINE_IMAGE_BYTES = 1024 * 1024
ALLOWED_RICH_MENU_SIZES = {(2500, 843), (2500, 1686)}


class FileSystemRichMenuImageStore:
    def __init__(self, storage_root: str | Path) -> None:
        self._root = Path(storage_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def materialize(
        self,
        definition_json: str,
        object_reference: str | None = None,
    ) -> str:
        menu = json.loads(definition_json)
        appearance = menu.get("appearance", {})
        if appearance.get("image_mode", "generated") == "uploaded":
            reference = object_reference or appearance.get("image_object_reference")
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError("uploaded Rich Menu requires an image object reference")
            self.load(reference)
            return reference
        content = render_rich_menu_image(menu)
        digest = hashlib.sha256(content).hexdigest()
        reference = f"rich_menu/{digest[:2]}/{digest}.jpg"
        target = self._target(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise RuntimeError("Rich Menu image object reference collision")
            return reference
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return reference

    def load(self, object_reference: str) -> tuple[bytes, str]:
        target = self._target(object_reference)
        if not target.is_file():
            raise FileNotFoundError("Rich Menu image object does not exist")
        suffix = target.suffix.lower()
        content_type = "image/png" if suffix == ".png" else "image/jpeg"
        return target.read_bytes(), content_type

    def _target(self, object_reference: str) -> Path:
        if not isinstance(object_reference, str) or not object_reference.strip():
            raise ValueError("Rich Menu image object reference is required")
        target = (self._root / object_reference).resolve()
        if self._root != target and self._root not in target.parents:
            raise ValueError("Rich Menu image path escaped configured storage root")
        return target


def _get_icon_for_label(label: str) -> str:
    if "通報" in label or "異常" in label or "警報" in label:
        return "🚨"
    if "看板" in label or "報表" in label or "數據" in label or "營運" in label:
        return "📊"
    if "修改" in label or "異動" in label:
        return "✏️"
    if "登記" in label or "申請" in label:
        return "📝"
    if "說明" in label or "FAQ" in label:
        return "🔍"
    if "客服" in label or "諮詢" in label:
        return "💬"
    if "訂單" in label or "案件" in label:
        return "📦"
    if "排班" in label or "日曆" in label:
        return "📅"
    if "請假" in label or "休假" in label:
        return "🏖️"
    if "薪資" in label or "請款" in label or "明細" in label:
        return "💵"
    if "契約" in label or "合約" in label:
        return "📑"
    if "評價" in label or "滿意度" in label:
        return "⭐"
    if "審核" in label or "調度" in label or "確認" in label:
        return "📋"
    if "一般用戶" in label or "會員" in label or "用戶" in label:
        return "👥"
    if "月嫂" in label:
        return "👩‍🍼"
    if "工會" in label:
        return "🛡️"
    return "📌"


def _find_emoji_font(size: int = 140) -> ImageFont.FreeTypeFont | None:
    for path in (
        "C:/Windows/Fonts/seguiemj.ttf",
        "seguiemj.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/truetype/google-noto-color-emoji/NotoColorEmoji.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return None


def _find_text_font(size: int = 76) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "C:/Windows/Fonts/msjhbd.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "/Library/Fonts/Microsoft JhengHei Bold.ttf",
        "/Library/Fonts/Microsoft JhengHei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "msjhbd.ttc",
        "msjh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_rich_menu_image(menu: dict[str, object]) -> bytes:
    width = int(menu["size"]["width"])
    height = int(menu["size"]["height"])
    if (width, height) not in ALLOWED_RICH_MENU_SIZES:
        raise ValueError("Rich Menu image size is unsupported")

    appearance = menu.get("appearance")
    bg_color = (
        appearance.get("background_color", "#F4EFEB")
        if isinstance(appearance, dict) and appearance.get("background_color")
        else "#F4EFEB"
    )
    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    buttons = menu.get("buttons", [])
    margin = 16

    for button in buttons:
        bounds = button["bounds"]
        bx, by = int(bounds["x"]), int(bounds["y"])
        bw, bh = int(bounds["width"]), int(bounds["height"])
        card_box = [bx + margin, by + margin, bx + bw - margin, by + bh - margin]
        is_compact = bh < 700

        radius = int(button.get("border_radius", 0) or 0)
        card_radius = min(radius, 44) if radius > 0 else (34 if is_compact else 44)

        # 1. 繪製純白卡片底圖與柔和邊框
        draw.rounded_rectangle(
            card_box,
            radius=card_radius,
            fill="#FFFFFF",
            outline="#E5DCD4",
            width=3,
        )

        # 2. 繪製頂部品牌強調色條
        accent_color = button.get("background_color") or "#FF7F50"
        accent_h = 10 if is_compact else 14
        draw.rounded_rectangle(
            [card_box[0] + 24, card_box[1] + 4, card_box[2] - 24, card_box[1] + accent_h + 4],
            radius=6,
            fill=accent_color,
        )

        label = str(button.get("label", ""))
        icon = _get_icon_for_label(label)
        card_center_x = bx + bw / 2
        card_center_y = by + bh / 2

        # 3. 繪製圓形底圖與圖示 (Emoji / Icon)
        emoji_size = 110 if is_compact else 145
        emoji_font = _find_emoji_font(emoji_size)
        circle_r = 72 if is_compact else 100
        circle_y = card_center_y - (50 if is_compact else 80)

        draw.ellipse(
            [
                card_center_x - circle_r,
                circle_y - circle_r,
                card_center_x + circle_r,
                circle_y + circle_r,
            ],
            fill="#FFF7F2",
        )

        if emoji_font:
            try:
                e_box = draw.textbbox((0, 0), icon, font=emoji_font)
                ew = e_box[2] - e_box[0]
                eh = e_box[3] - e_box[1]
                draw.text(
                    (card_center_x - ew / 2 - e_box[0], circle_y - eh / 2 - e_box[1]),
                    icon,
                    font=emoji_font,
                    embedded_color=True,
                )
            except Exception:
                pass

        # 4. 繪製主標題文字
        title_font_size = 58 if is_compact else 76
        title_font = _find_text_font(title_font_size)
        t_box = draw.textbbox((0, 0), label, font=title_font)
        tw = t_box[2] - t_box[0]
        th = t_box[3] - t_box[1]

        # 若文字過長則動態微調字型
        if tw > (bw - margin * 2 - 40) and title_font_size > 40:
            title_font_size = int(title_font_size * 0.8)
            title_font = _find_text_font(title_font_size)
            t_box = draw.textbbox((0, 0), label, font=title_font)
            tw = t_box[2] - t_box[0]
            th = t_box[3] - t_box[1]

        ty = card_center_y + (54 if is_compact else 82)
        text_color = button.get("text_color")
        if not text_color or text_color == "#FFFFFF":
            text_color = "#2B211D"

        draw.text(
            (card_center_x - tw / 2 - t_box[0], ty),
            label,
            font=title_font,
            fill=text_color,
        )

        # 5. 繪製動作提示次標題
        action = button.get("action", {})
        action_type = action.get("type", "") if isinstance(action, dict) else ""
        sub_text = "線上服務 ›" if action_type == "uri" else "即時查詢 ›"
        sub_font_size = 32 if is_compact else 38
        sub_font = _find_text_font(sub_font_size)
        s_box = draw.textbbox((0, 0), sub_text, font=sub_font)
        sw = s_box[2] - s_box[0]
        draw.text(
            (card_center_x - sw / 2 - s_box[0], ty + th + (16 if is_compact else 22)),
            sub_text,
            font=sub_font,
            fill="#A89587",
        )

    return encode_line_jpeg(image)


def encode_line_jpeg(image: Image.Image) -> bytes:
    rgb = ImageOps.exif_transpose(image).convert("RGB")
    for quality in (92, 86, 80, 74, 68, 60):
        output = io.BytesIO()
        rgb.save(output, format="JPEG", quality=quality, optimize=True)
        data = output.getvalue()
        if len(data) <= MAX_LINE_IMAGE_BYTES:
            return data
    raise ValueError("Rich Menu image remains too large after encoding")


__all__ = [
    "ALLOWED_RICH_MENU_SIZES",
    "FileSystemRichMenuImageStore",
    "MAX_LINE_IMAGE_BYTES",
    "encode_line_jpeg",
    "render_rich_menu_image",
]

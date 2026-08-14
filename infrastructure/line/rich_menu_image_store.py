"""Content-addressed filesystem/NAS storage and renderer for Rich Menu images."""

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


def render_rich_menu_image(menu: dict[str, object]) -> bytes:
    width = int(menu["size"]["width"])
    height = int(menu["size"]["height"])
    if (width, height) not in ALLOWED_RICH_MENU_SIZES:
        raise ValueError("Rich Menu image size is unsupported")
    appearance = menu.get("appearance")
    background = appearance.get("background_color", "#F5F5F5") if isinstance(appearance, dict) else "#F5F5F5"
    image = Image.new("RGB", (width, height), color=background)
    draw = ImageDraw.Draw(image)
    for button in menu.get("buttons", []):
        bounds = button["bounds"]
        left, top = int(bounds["x"]), int(bounds["y"])
        button_width = int(bounds["width"])
        button_height = int(bounds["height"])
        right = left + int(bounds["width"])
        bottom = top + int(bounds["height"])
        draw.rectangle(
            [left, top, right, bottom],
            fill=button.get("background_color", "#4A90E2"),
            outline="#FFFFFF",
            width=4,
        )
        label = str(button["label"])
        font, text_box = _button_font_for_label(draw, label, button_width, button_height)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        draw.text(
            (
                left + (button_width - text_width) / 2 - text_box[0],
                top + (button_height - text_height) / 2 - text_box[1],
            ),
            label,
            fill=button.get("text_color", "#FFFFFF"),
            font=font,
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


def _button_font_for_label(
    draw: ImageDraw.ImageDraw,
    label: str,
    width: int,
    height: int,
):
    for size in range(min(300, int(height * 0.38)), 119, -8):
        font = _font(size)
        text_box = draw.textbbox((0, 0), label, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        if text_width <= width * 0.82 and text_height <= height * 0.58:
            return font, text_box
    font = _font(120)
    return font, draw.textbbox((0, 0), label, font=font)


def _font(size: int = 86):
    for name in (
        "/Library/Fonts/Microsoft JhengHei.ttf",
        "/Library/Fonts/Microsoft JhengHei Bold.ttf",
        "/Library/Fonts/msjh.ttc",
        "/Library/Fonts/msjhbd.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "msjh.ttc",
        "Microsoft JhengHei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


__all__ = [
    "ALLOWED_RICH_MENU_SIZES",
    "FileSystemRichMenuImageStore",
    "MAX_LINE_IMAGE_BYTES",
    "encode_line_jpeg",
    "render_rich_menu_image",
]

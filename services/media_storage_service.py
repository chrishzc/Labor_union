"""Validated media storage; database stores metadata while files stay outside Git."""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from pathlib import Path
from typing import Any

import pymysql
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from services.db_service import get_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_LINE_IMAGE_BYTES = 1024 * 1024
ALLOWED_RICH_MENU_SIZES = {(2500, 843), (2500, 1686)}


class MediaValidationError(ValueError):
    pass


class MediaAssetNotFoundError(LookupError):
    pass


def media_storage_root() -> Path:
    configured = os.getenv("MEDIA_STORAGE_ROOT", ".local_media").strip() or ".local_media"
    root = Path(configured)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _font(size: int = 86):
    for name in (
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


def render_rich_menu_image(menu: dict[str, Any]) -> bytes:
    width = int(menu["size"]["width"])
    height = int(menu["size"]["height"])
    if (width, height) not in ALLOWED_RICH_MENU_SIZES:
        raise MediaValidationError("Rich Menu 圖片尺寸不受支援")
    image = Image.new(
        "RGB",
        (width, height),
        color=menu.get("appearance", {}).get("background_color", "#F5F5F5"),
    )
    draw = ImageDraw.Draw(image)
    font = _font()
    for button in menu.get("buttons", []):
        bounds = button["bounds"]
        left, top = int(bounds["x"]), int(bounds["y"])
        right = left + int(bounds["width"])
        bottom = top + int(bounds["height"])
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
                left + (int(bounds["width"]) - text_width) / 2,
                top + (int(bounds["height"]) - text_height) / 2,
            ),
            label,
            fill=button.get("text_color", "#FFFFFF"),
            font=font,
        )
    return _encode_jpeg(image)


def _encode_jpeg(image: Image.Image) -> bytes:
    rgb = ImageOps.exif_transpose(image).convert("RGB")
    for quality in (92, 86, 80, 74, 68, 60):
        output = io.BytesIO()
        rgb.save(output, format="JPEG", quality=quality, optimize=True)
        data = output.getvalue()
        if len(data) <= MAX_LINE_IMAGE_BYTES:
            return data
    raise MediaValidationError("圖片重新編碼後仍超過 LINE Rich Menu 可接受大小")


def normalize_uploaded_rich_menu_image(
    content: bytes,
    *,
    expected_width: int,
    expected_height: int,
) -> bytes:
    if not content:
        raise MediaValidationError("圖片內容不可為空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise MediaValidationError("上傳圖片超過系統允許大小")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            if source.format not in {"JPEG", "PNG"}:
                raise MediaValidationError("只接受 JPEG 或 PNG 圖片")
            if source.size != (expected_width, expected_height):
                raise MediaValidationError(
                    f"圖片尺寸必須是 {expected_width}x{expected_height}"
                )
            return _encode_jpeg(source)
    except UnidentifiedImageError as exc:
        raise MediaValidationError("檔案不是有效圖片") from exc


def _safe_storage_path(storage_key: str) -> Path:
    root = media_storage_root()
    target = (root / storage_key).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MediaValidationError("媒體路徑超出受控儲存區") from exc
    return target


def _save_asset(
    content: bytes,
    *,
    menu_id: str,
    original_filename: str,
    width: int,
    height: int,
    created_by_admin_user_id: int | None,
    generated: bool,
) -> dict[str, Any]:
    storage_key = f"rich_menu/{menu_id}/{uuid.uuid4().hex}.jpg"
    target = _safe_storage_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, target)
    digest = hashlib.sha256(content).hexdigest()
    provider = os.getenv("MEDIA_STORAGE_PROVIDER", "local").strip().lower()
    if provider not in {"local", "nas"}:
        provider = "local"

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO media_assets (
                    category, owner_type, owner_id, storage_provider, storage_key,
                    original_filename, mime_type, file_size, sha256, width, height,
                    created_by_admin_user_id
                ) VALUES ('rich_menu','line_menu',%s,%s,%s,%s,'image/jpeg',%s,%s,%s,%s,%s)
                """,
                (
                    menu_id,
                    provider,
                    storage_key,
                    original_filename if not generated else f"generated-{menu_id}.jpg",
                    len(content),
                    digest,
                    width,
                    height,
                    created_by_admin_user_id,
                ),
            )
            asset_id = int(cursor.lastrowid)
        conn.commit()
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        conn.close()
    return get_media_asset(asset_id)


def store_uploaded_rich_menu_image(
    content: bytes,
    *,
    menu_id: str,
    original_filename: str,
    expected_width: int,
    expected_height: int,
    created_by_admin_user_id: int | None,
) -> dict[str, Any]:
    normalized = normalize_uploaded_rich_menu_image(
        content,
        expected_width=expected_width,
        expected_height=expected_height,
    )
    return _save_asset(
        normalized,
        menu_id=menu_id,
        original_filename=Path(original_filename).name,
        width=expected_width,
        height=expected_height,
        created_by_admin_user_id=created_by_admin_user_id,
        generated=False,
    )


def store_generated_rich_menu_image(
    menu: dict[str, Any],
    *,
    created_by_admin_user_id: int | None,
) -> dict[str, Any]:
    content = render_rich_menu_image(menu)
    return _save_asset(
        content,
        menu_id=menu["id"],
        original_filename=f"generated-{menu['id']}.jpg",
        width=int(menu["size"]["width"]),
        height=int(menu["size"]["height"]),
        created_by_admin_user_id=created_by_admin_user_id,
        generated=True,
    )


def get_media_asset(asset_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM media_assets WHERE id=%s AND deleted_at IS NULL",
                (asset_id,),
            )
            asset = cursor.fetchone()
        if not asset:
            raise MediaAssetNotFoundError(f"找不到媒體資產 #{asset_id}")
        return asset
    finally:
        conn.close()


def read_media_asset(asset_id: int) -> tuple[dict[str, Any], bytes]:
    asset = get_media_asset(asset_id)
    path = _safe_storage_path(asset["storage_key"])
    if not path.is_file():
        raise MediaAssetNotFoundError(f"媒體資產 #{asset_id} 的檔案不存在")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != asset["sha256"]:
        raise MediaValidationError(f"媒體資產 #{asset_id} 完整性驗證失敗")
    return asset, content


def delete_media_asset(asset_id: int) -> None:
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id FROM media_assets WHERE id=%s AND deleted_at IS NULL FOR UPDATE",
                (asset_id,),
            )
            if not cursor.fetchone():
                raise MediaAssetNotFoundError(f"找不到媒體資產 #{asset_id}")
            cursor.execute(
                """
                SELECT id FROM line_rich_menu_publications
                WHERE image_asset_id=%s AND is_current=TRUE LIMIT 1
                """,
                (asset_id,),
            )
            if cursor.fetchone():
                raise MediaValidationError("目前已發布的 Rich Menu 圖片不能刪除")
            cursor.execute(
                "UPDATE media_assets SET deleted_at=UTC_TIMESTAMP() WHERE id=%s",
                (asset_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

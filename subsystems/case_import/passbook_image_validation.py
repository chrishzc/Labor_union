"""
File: passbook_image_validation.py
Description: 驗證客戶存摺封面圖片的 magic bytes、MIME 與檔案大小上限。
"""
from __future__ import annotations

from pathlib import Path

MAX_PASSBOOK_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class PassbookImageValidationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def detect_passbook_image_mime(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_passbook_image_bytes(content: bytes, filename: str | None) -> tuple[str, str]:
    if not content:
        raise PassbookImageValidationError("passbook_image_empty", "存摺封面圖片不可為空白。")
    if len(content) > MAX_PASSBOOK_IMAGE_BYTES:
        raise PassbookImageValidationError(
            "passbook_image_too_large",
            "存摺封面圖片大小不可超過 5 MB。",
            status_code=413,
        )
    mime_type = detect_passbook_image_mime(content)
    if mime_type is None:
        raise PassbookImageValidationError(
            "passbook_image_invalid_type",
            "存摺封面只接受 JPG、PNG 或 WebP 圖片。",
        )
    stem = Path(filename or "passbook").stem.strip() or "passbook"
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)[:48] or "passbook"
    return f"{safe_stem}{_ALLOWED_EXTENSIONS[mime_type]}", mime_type

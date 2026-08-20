"""
File: liff_media_upload.py
Description: 驗證月嫂 LIFF 圖片並保存為受控 LINE media reference，不接受任意網址或 Base64。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from domains.line.identities import LineSourceIdentity, LineSourceType, LineUserId
from domains.line.media import (
    LineMediaCategory,
    LineMediaMetadata,
    LineMediaPolicy,
    validate_media_against_policy,
)
from shared_kernel.identities import IdempotencyKey


MEAL_PHOTO_POLICY = LineMediaPolicy(
    ("image/jpeg", "image/png", "image/webp"),
    10 * 1024 * 1024,
)


@dataclass(frozen=True, slots=True)
class LiffMealPhotoUpload:
    line_user_id: LineUserId
    content: bytes
    declared_content_type: str
    idempotency_key: IdempotencyKey


@dataclass(frozen=True, slots=True)
class LiffMealPhotoUploadResult:
    media_id: str
    content_type: str
    size_bytes: int
    outcome: str


def prepare_liff_meal_photo_upload(command: LiffMealPhotoUpload) -> LineMediaMetadata:
    if not command.content:
        raise ValueError("service_day_meal_photo_is_empty")
    detected_type = _image_content_type(command.content)
    if detected_type is None or detected_type != command.declared_content_type:
        raise ValueError("service_day_meal_photo_content_type_invalid")
    media_id = _media_id(command.line_user_id, command.idempotency_key)
    metadata = LineMediaMetadata(
        provider_media_id=media_id,
        source=LineSourceIdentity(
            LineSourceType.USER,
            command.line_user_id.value,
            command.line_user_id,
        ),
        content_type=detected_type,
        size_bytes=len(command.content),
        content_sha256=hashlib.sha256(command.content).hexdigest(),
        received_at=datetime.now(timezone.utc),
        category=LineMediaCategory.USER_UPLOAD,
    )
    validate_media_against_policy(metadata, MEAL_PHOTO_POLICY)
    return metadata


def existing_liff_upload_matches(
    metadata: LineMediaMetadata,
    command: LiffMealPhotoUpload,
) -> bool:
    return (
        metadata.source.user_id == command.line_user_id
        and metadata.content_type == command.declared_content_type
        and metadata.size_bytes == len(command.content)
        and metadata.content_sha256 == hashlib.sha256(command.content).hexdigest()
        and metadata.category is LineMediaCategory.USER_UPLOAD
    )


def _media_id(line_user_id: LineUserId, key: IdempotencyKey) -> str:
    digest = hashlib.sha256(
        f"{line_user_id.value}:{key.value}".encode("utf-8")
    ).hexdigest()
    return f"liff-upload:{digest}"


def _image_content_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


__all__ = [
    "LiffMealPhotoUpload",
    "LiffMealPhotoUploadResult",
    "MEAL_PHOTO_POLICY",
    "existing_liff_upload_matches",
    "prepare_liff_meal_photo_upload",
]

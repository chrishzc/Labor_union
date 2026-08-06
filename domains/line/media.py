"""Pure LINE media metadata and retention validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineSourceIdentity
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
    require_sha256_hex,
)

_MEDIA_ID_MAXIMUM_LENGTH = 191
_CONTENT_TYPE_MAXIMUM_LENGTH = 100
_OWNER_REFERENCE_MAXIMUM_LENGTH = 191


class LineMediaCategory(StrEnum):
    USER_UPLOAD = "user_upload"
    IDENTITY_EVIDENCE = "identity_evidence"
    ORDER_ATTACHMENT = "order_attachment"
    RICH_MENU_IMAGE = "rich_menu_image"
    CUSTOMER_SERVICE_ATTACHMENT = "customer_service_attachment"
    UNCLASSIFIED = "unclassified"


class LineMediaPolicyViolation(ValueError):
    """Raised when media metadata violates a configured policy."""


@dataclass(frozen=True, slots=True)
class LineMediaPolicy:
    allowed_content_types: tuple[str, ...]
    maximum_size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_content_types, tuple):
            raise TypeError("LINE media allowed content types must be a tuple")
        if not self.allowed_content_types:
            raise ValueError("LINE media policy requires allowed content types")
        normalized = tuple(_content_type(value) for value in self.allowed_content_types)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("LINE media content types must be sorted and unique")
        require_positive_integer(self.maximum_size_bytes, "LINE media maximum size")


@dataclass(frozen=True, slots=True)
class LineMediaMetadata:
    provider_media_id: str
    source: LineSourceIdentity
    content_type: str
    size_bytes: int
    content_sha256: str
    received_at: datetime
    category: LineMediaCategory
    owner_type: str | None = None
    owner_reference: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(
            self.provider_media_id,
            "LINE provider media ID",
            _MEDIA_ID_MAXIMUM_LENGTH,
        )
        _content_type(self.content_type)
        require_positive_integer(self.size_bytes, "LINE media size")
        require_sha256_hex(self.content_sha256, "LINE media content hash")
        _require_aware_datetime(self.received_at)
        _validate_media_owner(self.owner_type, self.owner_reference)
        if not isinstance(self.category, LineMediaCategory):
            raise TypeError("LINE media category is invalid")


def validate_media_against_policy(
    metadata: LineMediaMetadata,
    policy: LineMediaPolicy,
) -> None:
    if metadata.content_type not in policy.allowed_content_types:
        raise LineMediaPolicyViolation("LINE media content type is not allowed")
    if metadata.size_bytes > policy.maximum_size_bytes:
        raise LineMediaPolicyViolation("LINE media exceeds maximum size")


def _content_type(value: object) -> str:
    normalized = require_canonical_text(
        value,
        "LINE media content type",
        _CONTENT_TYPE_MAXIMUM_LENGTH,
    )
    if normalized != normalized.lower() or "/" not in normalized:
        raise ValueError("LINE media content type must be lowercase MIME type")
    return normalized


def _validate_media_owner(
    owner_type: str | None,
    owner_reference: str | None,
) -> None:
    if (owner_type is None) != (owner_reference is None):
        raise ValueError("LINE media owner type and reference must appear together")
    if owner_type is None or owner_reference is None:
        return
    require_canonical_text(owner_type, "LINE media owner type", _OWNER_REFERENCE_MAXIMUM_LENGTH)
    require_canonical_text(
        owner_reference,
        "LINE media owner reference",
        _OWNER_REFERENCE_MAXIMUM_LENGTH,
    )


def _require_aware_datetime(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("LINE media received_at must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError("LINE media received_at must have a UTC offset")
    return value


__all__ = [
    "LineMediaCategory",
    "LineMediaMetadata",
    "LineMediaPolicy",
    "LineMediaPolicyViolation",
    "validate_media_against_policy",
]

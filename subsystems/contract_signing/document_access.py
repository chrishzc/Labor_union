"""Create opaque, recipient-bound document access credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import secrets


_MINIMUM_TTL = timedelta(minutes=5)
_MAXIMUM_TTL = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ContractDocumentAccessCredential:
    raw_token: str
    token_sha256: str
    expires_at: datetime


def create_document_access_credential(
    *,
    now: datetime,
    ttl: timedelta,
) -> ContractDocumentAccessCredential:
    _require_aware_time(now)
    _require_safe_ttl(ttl)
    raw_token = secrets.token_urlsafe(32)
    return ContractDocumentAccessCredential(
        raw_token,
        hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        now + ttl,
    )


def token_matches_credential(raw_token: str, token_sha256: str) -> bool:
    if not isinstance(raw_token, str) or not raw_token:
        return False
    actual = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return secrets.compare_digest(actual, token_sha256)


def _require_aware_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("contract document access time must be timezone-aware")


def _require_safe_ttl(value: timedelta) -> None:
    if not _MINIMUM_TTL <= value <= _MAXIMUM_TTL:
        raise ValueError("contract document access TTL is outside the allowed range")

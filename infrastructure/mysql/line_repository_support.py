"""Shared row, JSON, identity, and UTC helpers for LINE MySQL adapters."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from typing import Any

from domains.line.identities import (
    LineGroupId,
    LineRoomId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.delivery import LineRecipient, LineRecipientType


def require_row(row: object, error_code: str) -> Mapping[str, Any]:
    if not isinstance(row, Mapping):
        raise LookupError(error_code)
    return row


def optional_row(row: object) -> Mapping[str, Any] | None:
    return row if isinstance(row, Mapping) else None


def canonical_json_value(value: object) -> str:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("LINE persisted JSON must be an object")
    return json.dumps(
        dict(parsed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def database_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("LINE datetime must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def source_identity(
    source_type: str,
    source_id: str,
    source_user_id: str | None,
) -> LineSourceIdentity:
    user_id = LineUserId(source_user_id) if source_user_id else None
    return LineSourceIdentity(LineSourceType(source_type), source_id, user_id)


def recipient(recipient_type: str, identity: str) -> LineRecipient:
    kind = LineRecipientType(recipient_type)
    identity_type = {
        LineRecipientType.USER: LineUserId,
        LineRecipientType.GROUP: LineGroupId,
        LineRecipientType.ROOM: LineRoomId,
    }[kind]
    return LineRecipient(kind, identity_type(identity))


def mysql_error_code(error: BaseException) -> int | None:
    if error.args and isinstance(error.args[0], int):
        return error.args[0]
    return None


__all__ = [
    "aware_utc",
    "canonical_json_value",
    "database_utc",
    "mysql_error_code",
    "optional_row",
    "recipient",
    "require_row",
    "source_identity",
]

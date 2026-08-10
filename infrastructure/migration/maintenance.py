"""Maintenance-window and source-principal safety contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


_WRITE_PRIVILEGES = frozenset(
    {
        "ALTER",
        "ALTER ROUTINE",
        "CREATE",
        "CREATE ROUTINE",
        "CREATE TEMPORARY TABLES",
        "CREATE VIEW",
        "DELETE",
        "DROP",
        "EVENT",
        "EXECUTE",
        "FILE",
        "GRANT OPTION",
        "INDEX",
        "INSERT",
        "LOCK TABLES",
        "REFERENCES",
        "RELOAD",
        "SHUTDOWN",
        "SUPER",
        "SYSTEM_VARIABLES_ADMIN",
        "TRIGGER",
        "UPDATE",
    }
)


@dataclass(frozen=True, slots=True)
class SourcePrincipalEvidence:
    principal: str
    source_database: str
    privileges: frozenset[str]


@dataclass(frozen=True, slots=True)
class MaintenanceWindowToken:
    token_id: str
    source_database: str
    source_schema_sha256: str
    source_data_sha256: str
    write_freeze_started_at: str
    expires_at: str
    issuer: str
    fingerprint: str

    def canonical_payload(self) -> dict[str, str]:
        return {
            "expires_at": self.expires_at,
            "issuer": self.issuer,
            "source_data_sha256": self.source_data_sha256,
            "source_database": self.source_database,
            "source_schema_sha256": self.source_schema_sha256,
            "token_id": self.token_id,
            "write_freeze_started_at": self.write_freeze_started_at,
        }


def validate_source_read_only_principal(
    evidence: SourcePrincipalEvidence,
) -> SourcePrincipalEvidence:
    normalized = frozenset(value.upper() for value in evidence.privileges)
    if "SELECT" not in normalized:
        raise ValueError("source principal lacks SELECT privilege")
    forbidden = sorted(normalized & _WRITE_PRIVILEGES)
    if forbidden:
        raise ValueError(
            "source principal has write privileges: " + ",".join(forbidden)
        )
    return evidence


def issue_maintenance_window_token(
    *,
    token_id: str,
    source_database: str,
    source_schema_sha256: str,
    source_data_sha256: str,
    write_freeze_started_at: str,
    expires_at: str,
    issuer: str,
) -> MaintenanceWindowToken:
    fields = {
        "expires_at": expires_at,
        "issuer": issuer,
        "source_data_sha256": source_data_sha256,
        "source_database": source_database,
        "source_schema_sha256": source_schema_sha256,
        "token_id": token_id,
        "write_freeze_started_at": write_freeze_started_at,
    }
    return MaintenanceWindowToken(**fields, fingerprint=_fingerprint(fields))


def validate_maintenance_window_token(
    token: MaintenanceWindowToken,
    *,
    source_database: str,
    source_schema_sha256: str,
    source_data_sha256: str,
    now: datetime,
) -> MaintenanceWindowToken:
    _validate_token_fingerprint(token)
    _validate_source_facts(
        token,
        source_database,
        source_schema_sha256,
        source_data_sha256,
    )
    expires_at = _parse_utc(token.expires_at)
    started_at = _parse_utc(token.write_freeze_started_at)
    _validate_active_window(started_at, expires_at, now)
    return token


def _validate_active_window(
    started_at: datetime,
    expires_at: datetime,
    now: datetime,
) -> None:
    current_time = _require_utc(now)
    if current_time < started_at or current_time >= expires_at:
        raise ValueError("maintenance window token is not active")


def _validate_token_fingerprint(token: MaintenanceWindowToken) -> None:
    if _fingerprint(token.canonical_payload()) != token.fingerprint:
        raise ValueError("maintenance window token fingerprint mismatch")


def _validate_source_facts(
    token: MaintenanceWindowToken,
    database: str,
    schema_sha256: str,
    data_sha256: str,
) -> None:
    expected = (database, schema_sha256, data_sha256)
    actual = (
        token.source_database,
        token.source_schema_sha256,
        token.source_data_sha256,
    )
    if actual != expected:
        raise ValueError("maintenance window source facts are stale")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("maintenance token timestamp is invalid") from exc
    return _require_utc(parsed)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("maintenance token timestamps must be UTC")
    return value


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

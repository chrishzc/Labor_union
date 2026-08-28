"""
File: case_anomaly_readback.py
Description: 組合單一案件的唯讀異常回讀並對未解析綁定 fail closed。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Protocol

from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_sha256_hex,
)


_CASE_NUMBER_MAXIMUM_LENGTH = 50
_IDENTITY_MAXIMUM_LENGTH = 191

SUPPORTED_CANCELLATION_DEFINITIONS = (
    "CLIENTPAYABLE-001",
    "CLIENTREFUND-001",
    "HISTORICAL-ORDER-001",
    "IMPORT-004",
    "PAYOUT-001",
    "PAYOUT-002",
    "RECEIVABLE-001",
    "RETURN-001",
    "SCHEDULE-002",
    "SCHEDULE-003",
    "SCHEDULE-006",
    "client_over_refund_recovery_open",
    "client_refund_underpayment",
    "finance_import_manual_review",
    "staff_overpayment_recovery_open",
    "staff_payout_underpayment",
)


class CaseAnomalyReadbackStatus(StrEnum):
    COMPLETE = "complete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CaseAnomalyAlert:
    definition_code: str
    fingerprint: str
    source_identity: str
    source_version: int
    workflow_status: str

    def __post_init__(self) -> None:
        require_canonical_text(self.definition_code, "definition code", _IDENTITY_MAXIMUM_LENGTH)
        require_sha256_hex(self.fingerprint, "alert fingerprint")
        require_canonical_text(self.source_identity, "source identity", _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.source_version, "source version")
        require_canonical_text(self.workflow_status, "workflow status", 32)


@dataclass(frozen=True, slots=True)
class CaseAnomalyDefinitionRead:
    definition_code: str
    alerts: tuple[CaseAnomalyAlert, ...] = ()
    source_versions: tuple[tuple[str, int], ...] = ()
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.definition_code, "definition code", _IDENTITY_MAXIMUM_LENGTH)
        if self.alerts != tuple(sorted(self.alerts, key=lambda item: item.fingerprint)):
            raise ValueError("case anomaly alerts must be sorted")
        if self.source_versions != tuple(sorted(self.source_versions)):
            raise ValueError("case anomaly source versions must be sorted")
        for identity, version in self.source_versions:
            require_canonical_text(identity, "source version identity", _IDENTITY_MAXIMUM_LENGTH)
            require_nonnegative_integer(version, "source version")
        if self.unresolved_reason is not None:
            require_canonical_text(self.unresolved_reason, "unresolved reason", 191)
            if self.alerts:
                raise ValueError("unresolved definition cannot contain alerts")

    @property
    def resolved(self) -> bool:
        return self.unresolved_reason is None


@dataclass(frozen=True, slots=True)
class CaseAnomalyReadback:
    case_no: str
    resolved_alerts: tuple[CaseAnomalyAlert, ...]
    unresolved_definitions: tuple[tuple[str, str], ...]
    status: CaseAnomalyReadbackStatus
    source_versions: tuple[tuple[str, int], ...]
    read_at: datetime

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if self.resolved_alerts != tuple(
            sorted(self.resolved_alerts, key=lambda item: (item.definition_code, item.fingerprint))
        ):
            raise ValueError("case anomaly alerts must be sorted")
        if self.unresolved_definitions != tuple(sorted(self.unresolved_definitions)):
            raise ValueError("unresolved definitions must be sorted")
        for code, reason in self.unresolved_definitions:
            require_canonical_text(code, "unresolved definition code", _IDENTITY_MAXIMUM_LENGTH)
            require_canonical_text(reason, "unresolved definition reason", 191)
        if self.source_versions != tuple(sorted(self.source_versions)):
            raise ValueError("source versions must be sorted")
        if self.read_at.tzinfo is None:
            raise ValueError("read timestamp must be timezone aware")
        expected = (
            CaseAnomalyReadbackStatus.UNAVAILABLE
            if self.unresolved_definitions
            else CaseAnomalyReadbackStatus.COMPLETE
        )
        if self.status is not expected:
            raise ValueError("case anomaly readback status does not match unresolved definitions")


class CaseAnomalyReadSource(Protocol):
    def read_definition(
        self, case_no: str, definition_code: str, *, as_of: date
    ) -> CaseAnomalyDefinitionRead: ...


def resolve_case_anomalies(
    case_no: str,
    requested_definitions: Iterable[str],
    source: CaseAnomalyReadSource,
    *,
    as_of: date,
    read_at: datetime | None = None,
) -> CaseAnomalyReadback:
    """Resolve one case through definition-specific canonical read ports only."""

    require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
    if type(as_of) is not date:
        raise TypeError("as_of must be a business date")
    if isinstance(requested_definitions, (str, bytes)):
        raise TypeError("requested definitions must be an iterable of codes")
    codes = tuple(sorted(set(requested_definitions)))
    if not codes:
        raise ValueError("requested definitions must not be empty")
    for code in codes:
        require_canonical_text(code, "definition code", _IDENTITY_MAXIMUM_LENGTH)

    alerts: list[CaseAnomalyAlert] = []
    unresolved: list[tuple[str, str]] = []
    versions: list[tuple[str, int]] = []
    for code in codes:
        if code not in SUPPORTED_CANCELLATION_DEFINITIONS:
            unresolved.append((code, "definition_not_in_cancellation_readback"))
            continue
        try:
            result = source.read_definition(case_no, code, as_of=as_of)
        except Exception:
            unresolved.append((code, "canonical_read_unavailable"))
            continue
        if not isinstance(result, CaseAnomalyDefinitionRead):
            unresolved.append((code, "canonical_read_shape_invalid"))
            continue
        if result.definition_code != code:
            unresolved.append((code, "definition_identity_mismatch"))
            continue
        if not result.resolved:
            unresolved.append((code, result.unresolved_reason or "canonical_binding_unavailable"))
            continue
        alerts.extend(result.alerts)
        versions.extend(result.source_versions)

    normalized_alerts = tuple(
        sorted(alerts, key=lambda item: (item.definition_code, item.fingerprint))
    )
    normalized_versions = tuple(sorted(set(versions)))
    normalized_unresolved = tuple(sorted(set(unresolved)))
    timestamp = read_at or datetime.now(timezone.utc)
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        raise ValueError("read timestamp must be timezone aware")
    return CaseAnomalyReadback(
        case_no=case_no,
        resolved_alerts=normalized_alerts,
        unresolved_definitions=normalized_unresolved,
        status=(
            CaseAnomalyReadbackStatus.UNAVAILABLE
            if normalized_unresolved
            else CaseAnomalyReadbackStatus.COMPLETE
        ),
        source_versions=normalized_versions,
        read_at=timestamp,
    )


class CaseAnomalyReadbackService:
    """Small service wrapper used by owner workflows without an API dependency."""

    def __init__(self, source: CaseAnomalyReadSource) -> None:
        self._source = source

    def resolve_case_anomalies(
        self,
        case_no: str,
        requested_definitions: Iterable[str],
        *,
        as_of: date,
        read_at: datetime | None = None,
    ) -> CaseAnomalyReadback:
        return resolve_case_anomalies(
            case_no, requested_definitions, self._source, as_of=as_of, read_at=read_at
        )


__all__ = [
    "CaseAnomalyAlert",
    "CaseAnomalyDefinitionRead",
    "CaseAnomalyReadSource",
    "CaseAnomalyReadback",
    "CaseAnomalyReadbackService",
    "CaseAnomalyReadbackStatus",
    "SUPPORTED_CANCELLATION_DEFINITIONS",
    "resolve_case_anomalies",
]

"""Source safety evidence for preserve-data planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from infrastructure.migration.maintenance import (
    MaintenanceWindowToken,
    SourcePrincipalEvidence,
    validate_maintenance_window_token,
    validate_source_read_only_principal,
)


@dataclass(frozen=True, slots=True)
class SourceSafetyReceipt:
    source_database: str
    principal: str
    source_schema_sha256: str
    source_data_sha256: str
    maintenance_token_id: str
    maintenance_token_fingerprint: str
    status: str = "passed"


def build_source_safety_receipt(
    plan: Mapping[str, Any],
    principal_evidence: SourcePrincipalEvidence,
    maintenance_token: MaintenanceWindowToken,
    *,
    now: datetime,
) -> SourceSafetyReceipt:
    principal = validate_source_read_only_principal(principal_evidence)
    database = str((plan.get("source") or {}).get("database") or "")
    schema_sha256 = str(plan.get("source_schema_sha256") or "")
    data_sha256 = fingerprint_source_data_evidence(
        plan.get("source_data") or {}
    )
    validate_maintenance_window_token(
        maintenance_token,
        source_database=database,
        source_schema_sha256=schema_sha256,
        source_data_sha256=data_sha256,
        now=now,
    )
    if principal.source_database != database:
        raise ValueError("source principal database identity mismatch")
    return SourceSafetyReceipt(
        source_database=database,
        principal=principal.principal,
        source_schema_sha256=schema_sha256,
        source_data_sha256=data_sha256,
        maintenance_token_id=maintenance_token.token_id,
        maintenance_token_fingerprint=maintenance_token.fingerprint,
    )


def fingerprint_source_data_evidence(evidence: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        evidence,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


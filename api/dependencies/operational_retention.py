"""Composition root for operational retention sources and audit evidence."""

from __future__ import annotations

import os
from pathlib import Path

from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.runtime.operational_retention import (
    ManagedLogRetentionSource,
    MySqlKnowledgeRetentionSource,
    MySqlRetentionEvidenceStore,
)
from subsystems.runtime_governance.operational_retention import OperationalRetentionApplication


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def operational_retention_application() -> OperationalRetentionApplication:
    db_high = _optional_positive_int("OPERATIONAL_RETENTION_DB_HIGH_WATER_BYTES")
    db_low = _optional_positive_int("OPERATIONAL_RETENTION_DB_LOW_WATER_BYTES")
    file_high = _optional_positive_int("OPERATIONAL_RETENTION_FILE_HIGH_WATER_BYTES")
    file_low = _optional_positive_int("OPERATIONAL_RETENTION_FILE_LOW_WATER_BYTES")
    segment_max = _optional_positive_int("OPERATIONAL_RETENTION_LOG_SEGMENT_MAX_BYTES")
    chroma_path = _configured_path(os.getenv("KNOWLEDGE_CHROMA_PATH", "db/chroma_knowledge"))
    sources = (
        MySqlKnowledgeRetentionSource(
            get_connection,
            ChromaKnowledgeGateway(str(chroma_path)),
            high_water_bytes=db_high,
            low_water_bytes=db_low,
        ),
        ManagedLogRetentionSource(
            _log_roots(),
            high_water_bytes=file_high,
            low_water_bytes=file_low,
            segment_max_bytes=segment_max,
        ),
    )
    return OperationalRetentionApplication(sources, MySqlRetentionEvidenceStore(get_connection))


def automatic_retention_enabled() -> bool:
    return os.getenv("OPERATIONAL_RETENTION_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_automatic_retention_cycle() -> int:
    if not automatic_retention_enabled():
        return 0
    receipts = operational_retention_application().run_automatic()
    return sum(receipt.deleted_count for receipt in receipts)


def _log_roots() -> tuple[Path, ...]:
    raw = os.getenv("OPERATIONAL_RETENTION_LOG_ROOTS", "").strip()
    if not raw:
        return ()
    return tuple(
        _configured_path(value)
        for value in (part.strip() for part in raw.split(os.pathsep))
        if value
    )


def _configured_path(value: str) -> Path:
    path = Path(value.strip())
    return path if path.is_absolute() else PROJECT_ROOT / path


def _optional_positive_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


__all__ = [
    "automatic_retention_enabled",
    "operational_retention_application",
    "run_automatic_retention_cycle",
]

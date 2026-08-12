"""Rebuild projections that have no preserved root facts in a validation dataset."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json

from scripts.plan_legacy_ui_dataset_integration import require_target_database


PROJECTION_TABLES = (
    "anomaly_current_alerts",
    "client_deposit_settlement_projection",
    "scheduling_effective_occupancy",
)


def rebuild_preserved_root_projections(connection, target_database: str) -> dict[str, object]:
    target = require_target_database(target_database)
    with connection.cursor() as cursor:
        before = _projection_row_counts(cursor, target)
        for table_name in PROJECTION_TABLES:
            cursor.execute(f"DELETE FROM `{target}`.`{table_name}`")
        after = _projection_row_counts(cursor, target)
    return verify_preserved_root_projections(after, before)


def verify_preserved_root_projections(
    projection_counts: Mapping[str, int],
    counts_before_rebuild: Mapping[str, int] | None = None,
) -> dict[str, object]:
    unknown = sorted(set(projection_counts) - set(PROJECTION_TABLES))
    missing = sorted(set(PROJECTION_TABLES) - set(projection_counts))
    populated = sorted(name for name, count in projection_counts.items() if count)
    if unknown or missing or populated:
        details = ",".join(unknown + missing + populated)
        raise RuntimeError("preserved-root projection rebuild verification failed: " + details)
    counts = {name: int(projection_counts[name]) for name in PROJECTION_TABLES}
    return {
        "contract": "labor-union-legacy-ui-projection-rebuild/v1",
        "projection_source": "preserved_roots_only",
        "projection_tables": list(PROJECTION_TABLES),
        "projection_counts_before_rebuild": dict(counts_before_rebuild or counts),
        "projection_counts_after_rebuild": counts,
        "projection_digest": _projection_digest(counts),
        "verified": True,
    }


def _projection_row_counts(cursor, target_database: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in PROJECTION_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM `{target_database}`.`{table_name}`")
        counts[table_name] = int(cursor.fetchone()[0])
    return counts


def _projection_digest(projection_counts: Mapping[str, int]) -> str:
    payload = json.dumps(
        dict(sorted(projection_counts.items())), separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

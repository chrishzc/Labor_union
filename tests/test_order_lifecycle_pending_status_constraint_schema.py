"""
File: test_order_lifecycle_pending_status_constraint_schema.py
Description: 驗證待補件 lifecycle event constraint successor、release與predecessor判定。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1013_order_lifecycle_pending_status_constraint.sql"
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_28_order_lifecycle_pending_status_v1.json"
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_28_order_lifecycle_pending_status_v1.descriptors.json"
)
CHECK_KEY = (
    "order_lifecycle_state_events",
    "chk_order_lifecycle_state_event_before_status",
)


def test_release_hashes_and_catalog_order_are_exact() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(
        (ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json").read_text(
            encoding="utf-8"
        )
    )
    names = [Path(path).name for path in assembly["active_bootstrap"]]

    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(
        SQL_PATH.read_bytes()
    ).hexdigest()
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert manifest["backfills"] == []
    assert names.index("1012_service_before_replacement.sql") < names.index(SQL_PATH.name)
    assert names[-1] == SQL_PATH.name


def test_descriptor_matches_full_canonical_lifecycle_checks() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH, ROOT
    ).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert released["tables"] == canonical["tables"] == {}
    assert released["checks"] == canonical["checks"]
    assert set(canonical["checks"]) == {CHECK_KEY}
    assert all("待補件" in clause for clause in canonical["checks"].values())


def test_release_scoped_snapshot_reads_show_create_for_check_only_parent(
    monkeypatch,
) -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH, ROOT
    ).owned_object_descriptors(ROOT)
    monkeypatch.setattr(migration, "OWNED_OBJECTS", released)

    assert migration._show_create_owned_table_names() == {
        "order_lifecycle_state_events"
    }


def test_predecessor_successor_and_drift_are_distinct() -> None:
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)
    predecessor = _snapshot(
        "before_status IN ('洽談中','訂單成立','服務中','訂單完成','訂單取消')"
    )
    successor = _snapshot(
        "before_status IN ('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消')"
    )
    drift = _snapshot("before_status IN ('待補件','洽談中')")

    assert migration._order_lifecycle_pending_status_constraint_state(
        predecessor, canonical
    ) == "absent"
    assert migration._order_lifecycle_pending_status_constraint_state(
        successor, canonical
    ) == "exact"
    assert migration._order_lifecycle_pending_status_constraint_state(
        drift, canonical
    ) == "drift"
    assert migration._order_lifecycle_pending_status_constraint_state(
        {"constraints": [], "show_create_tables": {}}, canonical
    ) == "drift"


def _snapshot(before: str) -> dict[str, object]:
    return {
        "constraints": [
            {
                "table_name": "order_lifecycle_state_events",
                "constraint_name": "chk_order_lifecycle_state_event_before_status",
                "constraint_type": "CHECK",
                "check_clause": before,
                "enforced": "YES",
            },
        ],
        "show_create_tables": {},
    }

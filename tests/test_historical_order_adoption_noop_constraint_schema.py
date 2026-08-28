"""
File: test_historical_order_adoption_noop_constraint_schema.py
Description: 驗證 1008 no-op adoption constraint successor、release 與 predecessor 判定。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1008_historical_order_adoption_noop_constraint.sql"
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_27_historical_order_adoption_noop_v1.json"
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_27_historical_order_adoption_noop_v1.descriptors.json"
)
ASSEMBLY_PATH = ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"
CUTOVER_PATH = ROOT / "db/cutover_releases/labor_union_validation_schema_v1.json"
CHECK_KEY = (
    "historical_order_adoption_receipts",
    "chk_historical_order_adoption_shape",
)


def test_release_and_fresh_catalog_preserve_1008_before_its_successor() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))
    cutover = json.loads(CUTOVER_PATH.read_text(encoding="utf-8"))

    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(
        SQL_PATH.read_bytes()
    ).hexdigest()
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert manifest["backfills"] == []
    artifact_names = [Path(path).name for path in assembly["active_bootstrap"]]
    assert artifact_names.index(SQL_PATH.name) < artifact_names.index(
        "1009_anomaly_reclassification_disposition.sql"
    )
    assert cutover["schema_parts"]["expected_count"] == len(
        assembly["active_bootstrap"]
    )
    assert cutover["schema_parts"]["terminal_artifact"] == (
        "1014_historical_baseline_projector_v2.sql"
    )


def test_released_descriptor_matches_canonical_check_contract() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH,
        ROOT,
    ).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert released["tables"] == canonical["tables"] == {}
    assert released["checks"] == canonical["checks"]
    assert set(canonical["checks"]) == {CHECK_KEY}


def test_constraint_preserves_changed_and_noop_adopted_shapes() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "DROP CHECK chk_historical_order_adoption_shape" in sql
    assert "lifecycle_event_id IS NULL" in sql
    assert "resulting_version = expected_version" in sql
    assert "lifecycle_event_id IS NOT NULL" in sql
    assert "resulting_version = expected_version + 1" in sql


def test_predecessor_successor_and_drift_are_distinct() -> None:
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)
    predecessor = (
        "(outcome = 'unmatched_case' AND lifecycle_event_id IS NULL "
        "AND expected_version IS NULL AND resulting_version IS NULL) OR "
        "(outcome = 'adopted' AND lifecycle_event_id IS NOT NULL "
        "AND expected_version IS NOT NULL AND resulting_version = "
        "expected_version + 1 AND case_no IS NOT NULL) OR (outcome IN "
        "('review_required','current_conflict') AND lifecycle_event_id IS NULL "
        "AND expected_version IS NOT NULL AND resulting_version = "
        "expected_version AND case_no IS NOT NULL)"
    )

    assert _state(predecessor, canonical) == "absent"
    assert _state(canonical["checks"][CHECK_KEY], canonical) == "exact"
    assert _state("outcome = 'adopted'", canonical) == "drift"
    assert migration._historical_order_adoption_noop_constraint_state(
        {"constraints": [], "show_create_tables": {}},
        canonical,
    ) == "drift"


def test_local_additive_metadata_state_uses_1008_predecessor_contract() -> None:
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)
    predecessor = (
        "(outcome = 'unmatched_case' AND lifecycle_event_id IS NULL "
        "AND expected_version IS NULL AND resulting_version IS NULL) OR "
        "(outcome = 'adopted' AND lifecycle_event_id IS NOT NULL "
        "AND expected_version IS NOT NULL AND resulting_version = "
        "expected_version + 1 AND case_no IS NOT NULL) OR (outcome IN "
        "('review_required','current_conflict') AND lifecycle_event_id IS NULL "
        "AND expected_version IS NOT NULL AND resulting_version = "
        "expected_version AND case_no IS NOT NULL)"
    )

    assert migration._metadata_state_for_artifact(
        {
            "constraints": [{
                "table_name": CHECK_KEY[0],
                "constraint_name": CHECK_KEY[1],
                "constraint_type": "CHECK",
                "check_clause": predecessor,
                "enforced": "YES",
            }],
            "show_create_tables": {},
        },
        canonical,
        SQL_PATH.name,
        defer_missing_triggers=False,
    ) == "absent"


def _state(clause: str, descriptor) -> str:
    return migration._historical_order_adoption_noop_constraint_state(
        {
            "constraints": [{
                "table_name": CHECK_KEY[0],
                "constraint_name": CHECK_KEY[1],
                "constraint_type": "CHECK",
                "check_clause": clause,
                "enforced": "YES",
            }],
            "show_create_tables": {},
        },
        descriptor,
    )

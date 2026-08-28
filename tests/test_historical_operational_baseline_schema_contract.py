"""
File: test_historical_operational_baseline_schema_contract.py
Description: 驗證 1010 歷史作業基準 release、不可變 storage、descriptor 與 canonical catalog。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1010_historical_operational_baseline.sql"
MANIFEST_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_08_28_historical_operational_baseline_v1.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_28_historical_operational_baseline_v1.descriptors.json"
)
ASSEMBLY_PATH = ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"
CUTOVER_PATH = ROOT / "db/cutover_releases/labor_union_validation_schema_v1.json"
TABLES = {
    "historical_order_operational_baseline_events",
    "historical_order_operational_baseline_receipts",
    "historical_order_operational_baseline_outbox",
}


def test_release_is_schema_only_hash_locked_and_in_the_preserve_chain() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == (
        "labor-union-historical-operational-baseline-2026-08-28-v1"
    )
    assert manifest["artifacts"] == [{
        "name": SQL_PATH.name,
        "relative_path": "db/schema_parts/1010_historical_operational_baseline.sql",
        "sha256": hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": (
            "forward-only-preserve-historical-operational-baseline-evidence"
        ),
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert MANIFEST_PATH.name in migration.DEFAULT_RELEASE_MANIFESTS
    release_index = migration.DEFAULT_RELEASE_MANIFESTS.index(MANIFEST_PATH.name)
    assert migration.DEFAULT_RELEASE_MANIFESTS[release_index - 1] == (
        "labor_union_2026_08_27_anomaly_reclassification_disposition_v1.json"
    )
    loaded = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert loaded.schema_paths(ROOT) == (SQL_PATH.resolve(),)


def test_descriptor_is_complete_and_matches_the_canonical_sql_contract() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH,
        ROOT,
    ).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert set(released["tables"]) == TABLES
    canonical_tables = {
        table: set(columns)
        for table, columns in canonical["tables"].items()
    }
    assert released["tables"] == canonical_tables
    for kind in ("indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"])
    assert canonical["parent_columns"] == {}


def test_event_receipt_and_outbox_enforce_the_b1_storage_boundary() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "prior_baseline_event_id BIGINT UNSIGNED NULL" in sql
    assert "UNIQUE KEY uq_historical_operational_baseline_prior_event" in sql
    assert "REFERENCES historical_order_operational_baseline_events(id)" in sql
    assert "REFERENCES historical_order_adoption_receipts(source_event_identity)" in sql
    assert "ON UPDATE RESTRICT ON DELETE RESTRICT" in sql
    assert "candidate_snapshot JSON NOT NULL" in sql
    assert "step_projection JSON NOT NULL" in sql
    assert "result_snapshot JSON NOT NULL" in sql
    assert "bounded_snapshot JSON NOT NULL" in sql
    assert "evidence_mode ENUM(" in sql
    assert "'historical_evidence_unavailable_accepted'" in sql
    assert "selected_step BETWEEN 1 AND 11" in sql
    assert "resulting_orders_version = expected_orders_version" in sql
    assert "INSERT INTO" not in sql
    assert "ALTER TABLE" not in sql


def test_business_rows_are_immutable_and_outbox_updates_metadata_only() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    for table in (
        "historical_order_operational_baseline_events",
        "historical_order_operational_baseline_receipts",
    ):
        assert f"{table} records cannot be updated" in sql
        assert f"{table} records cannot be deleted" in sql
    assert "trg_historical_operational_baseline_outbox_before_update" in sql
    for business_column in (
        "id", "event_id", "receipt_id", "intent_key", "intent_type",
        "bounded_snapshot", "created_at",
    ):
        assert f"OLD.{business_column} <=> NEW.{business_column}" in sql
    for delivery_column in ("published_at", "attempts", "last_error"):
        assert f"OLD.{delivery_column} <=> NEW.{delivery_column}" not in sql
    assert "historical_order_operational_baseline_outbox records cannot be deleted" in sql


def test_fresh_assembly_keeps_1010_before_1011_and_tracks_current_terminal() -> None:
    assembly = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))
    cutover = json.loads(CUTOVER_PATH.read_text(encoding="utf-8"))
    active_bootstrap = assembly["active_bootstrap"]
    baseline_index = active_bootstrap.index(
        "db/schema_parts/1010_historical_operational_baseline.sql"
    )

    assert active_bootstrap[baseline_index + 1].endswith(
        "1011_historical_baseline_projector.sql"
    )
    assert cutover["schema_parts"]["expected_count"] == len(
        active_bootstrap
    )
    assert cutover["schema_parts"]["terminal_artifact"] == Path(
        active_bootstrap[-1]
    ).name
    assert cutover["schema_parts"]["ordered_digest_sha256"] == (
        assembly["active_artifacts_sha256"]
    )
    assert cutover["schema_assembly"]["sha256"] == hashlib.sha256(
        ASSEMBLY_PATH.read_bytes()
    ).hexdigest()

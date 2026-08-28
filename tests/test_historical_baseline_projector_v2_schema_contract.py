"""Static contract checks for the additive 1013 projector persistence successor."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.build_validation_schema_release import verify_release
from scripts.schema_assembly import load_schema_assembly
from scripts.verify_validation_schema_manifest import load_manifest, verify_manifest
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1014_historical_baseline_projector_v2.sql"
MANIFEST_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_08_28_historical_baseline_projector_v2.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_28_historical_baseline_projector_v2.descriptors.json"
)

TABLES = {
    "historical_baseline_v2_occurrence_state_events",
    "historical_baseline_v2_projector_receipts",
    "historical_baseline_v2_active_membership_snapshots",
    "historical_baseline_v2_projector_deliveries",
    "historical_baseline_v2_source_checkpoints",
    "historical_baseline_v2_post_commit_readbacks",
}


def test_v2_release_is_hash_locked_schema_only_and_follows_1012() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == (
        "labor-union-historical-baseline-projector-2026-08-28-v2"
    )
    assert manifest["artifacts"] == [{
        "name": SQL_PATH.name,
        "relative_path": (
            "db/schema_parts/1014_historical_baseline_projector_v2.sql"
        ),
        "sha256": hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": (
            "forward-only-preserve-historical-baseline-projector-v1-and-v2-evidence"
        ),
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    release_index = migration.DEFAULT_RELEASE_MANIFESTS.index(MANIFEST_PATH.name)
    assert migration.DEFAULT_RELEASE_MANIFESTS[release_index - 1] == (
        "labor_union_2026_08_28_order_lifecycle_pending_status_v1.json"
    )
    loaded = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert loaded.schema_paths(ROOT) == (SQL_PATH.resolve(),)


def test_v2_descriptor_matches_every_canonical_owned_object() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH,
        ROOT,
    ).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert set(released["tables"]) == TABLES
    assert released["tables"] == {
        table: set(columns)
        for table, columns in canonical["tables"].items()
    }
    for kind in ("indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"])
    assert canonical["parent_columns"] == {}


def test_v2_is_the_fresh_assembly_and_validation_release_terminal() -> None:
    assembly = load_schema_assembly()
    validation_manifest = load_manifest()

    assert [path.name for path in assembly.active_artifact_paths[-3:]] == [
        "1012_service_before_replacement.sql",
        "1013_order_lifecycle_pending_status_constraint.sql",
        "1014_historical_baseline_projector_v2.sql",
    ]
    assert validation_manifest["schema_parts"]["terminal_artifact"] == SQL_PATH.name
    assert verify_manifest(validation_manifest) == []
    assert verify_release(validation_manifest) == []


def _table_block(sql: str, table: str) -> str:
    prefix = f"CREATE TABLE IF NOT EXISTS {table} ("
    start = sql.index(prefix) + len(prefix)
    depth = 1
    for offset, character in enumerate(sql[start:], start=start):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return sql[start:offset]
    raise AssertionError(f"unterminated CREATE TABLE for {table}")


def _has_column(block: str, column: str) -> bool:
    return re.search(rf"^\s*{re.escape(column)}\s", block, re.MULTILINE) is not None


def test_v2_artifact_is_additive_and_has_exact_table_set() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    created_tables = set(
        re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z0-9_]+)\s*\(", sql)
    )
    assert created_tables == TABLES
    assert "1011_historical_baseline_projector.sql" not in sql
    assert not re.search(r"^\s*ALTER\s+TABLE\b", sql, re.I | re.M)
    assert not re.search(r"^\s*DROP\s+TABLE\b", sql, re.I | re.M)
    assert not re.search(
        r"^\s*(?:INSERT\s+INTO|UPDATE\s+[a-z0-9_]+\s+SET|DELETE\s+FROM)\b",
        sql,
        re.I | re.M,
    )


def test_occurrence_state_is_lineage_bound_and_append_only() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    block = _table_block(sql, "historical_baseline_v2_occurrence_state_events")
    for column in (
        "state_event_identity",
        "occurrence_id",
        "prior_state_event_id",
        "case_no",
        "order_identity",
        "baseline_event_id",
        "catalog_identity",
        "catalog_version",
        "descriptor_identity",
        "contract_id",
        "contract_version",
        "terminal_predicate_id",
        "terminal_predicate_version",
        "owner_event_identity",
        "owner_source_version",
        "expected_state_version",
        "resulting_state_version",
        "state",
        "owner_binding_fingerprint",
        "fresh_readback_fingerprint",
    ):
        assert _has_column(block, column)
    assert "ENUM('opened', 'resolved', 'superseded')" in block
    assert "UNIQUE KEY uq_hbp_v2_state_occurrence_version" in block
    assert "FOREIGN KEY (" in block
    assert "REFERENCES historical_baseline_occurrences (" in block
    assert "REFERENCES historical_baseline_v2_occurrence_state_events (" in block
    assert "resulting_state_version = expected_state_version + 1" in block
    assert "prior_state_event_id IS NULL" in block
    assert "prior_state_event_id IS NOT NULL" in block
    assert "BEFORE UPDATE ON historical_baseline_v2_occurrence_state_events" in sql
    assert "BEFORE DELETE ON historical_baseline_v2_occurrence_state_events" in sql


def test_v2_receipt_separates_emitted_and_active_sets_and_allows_zero() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    block = _table_block(sql, "historical_baseline_v2_projector_receipts")
    for column in (
        "source_trigger_identity",
        "source_trigger_version",
        "payload_digest",
        "idempotency_key",
        "baseline_event_id",
        "baseline_receipt_id",
        "baseline_outbox_id",
        "whole_vector_fingerprint",
        "whole_vector_count",
        "emitted_occurrence_set_digest",
        "emitted_occurrence_set_count",
        "emitted_occurrence_identities",
        "active_membership_set_digest",
        "active_membership_set_count",
        "projection_sequence",
        "current_alert_fingerprint",
        "expected_readback_digest",
        "result_state",
    ):
        assert _has_column(block, column)
    assert "ENUM('projected', 'held_active')" in block
    assert "emitted_occurrence_set_count >= 0" in block
    assert "emitted_occurrence_identities JSON NOT NULL" in block
    assert "JSON_LENGTH(emitted_occurrence_identities)" in block
    assert "active_membership_set_count >= 0" in block
    assert "REFERENCES historical_order_operational_baseline_events(id)" in block
    assert "REFERENCES historical_order_operational_baseline_receipts(id)" in block
    assert "REFERENCES historical_order_operational_baseline_outbox(id)" in block
    assert "REFERENCES anomaly_current_alerts(fingerprint)" in block
    assert "BEFORE UPDATE ON historical_baseline_v2_projector_receipts" in sql
    assert "BEFORE DELETE ON historical_baseline_v2_projector_receipts" in sql


def test_alert_foreign_keys_use_the_parent_utf8mb4_collation() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    receipt = _table_block(sql, "historical_baseline_v2_projector_receipts")
    readback = _table_block(sql, "historical_baseline_v2_post_commit_readbacks")

    assert "current_alert_fingerprint CHAR(64) NOT NULL" in receipt
    assert "current_alert_fingerprint CHAR(64)\n        CHARACTER SET ascii" not in receipt
    assert "actual_current_alert_fingerprint CHAR(64) NULL" in readback
    assert "actual_current_alert_fingerprint CHAR(64)\n        CHARACTER SET ascii" not in readback


def test_membership_snapshot_is_per_receipt_and_has_no_global_occurrence_unique() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    block = _table_block(sql, "historical_baseline_v2_active_membership_snapshots")
    for column in (
        "membership_identity",
        "projector_receipt_id",
        "umbrella_identity",
        "set_ordinal",
        "occurrence_id",
        "case_no",
        "order_identity",
        "baseline_event_id",
        "catalog_identity",
        "catalog_version",
        "projection_sequence",
    ):
        assert _has_column(block, column)
    assert "UNIQUE KEY uq_hbp_v2_membership_receipt_ordinal" in block
    assert "UNIQUE KEY uq_hbp_v2_membership_receipt_occurrence" in block
    assert "UNIQUE KEY uq_hbp_v2_membership_occurrence" not in block
    assert "set_ordinal > 0" in block
    assert "BEFORE UPDATE ON historical_baseline_v2_active_membership_snapshots" in sql
    assert "BEFORE DELETE ON historical_baseline_v2_active_membership_snapshots" in sql


def test_delivery_uses_the_fixed_six_states_and_checkpoint_is_source_specific() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    delivery = _table_block(sql, "historical_baseline_v2_projector_deliveries")
    for column in (
        "source_trigger_identity",
        "payload_digest",
        "source_kind",
        "source_domain",
        "source_event_identity",
        "source_version",
        "partition_key",
        "delivery_status",
        "attempt_count",
        "max_attempts",
        "lease_owner",
        "lease_expires_at",
        "last_error_code",
    ):
        assert _has_column(delivery, column)
    assert (
        "'pending',\n        'processing',\n        'retryable_failed',\n"
        "        'committed_unverified',\n        'processed',\n        'dead_letter'"
    ) in delivery
    assert "UNIQUE KEY uq_hbp_v2_delivery_trigger" in delivery
    assert "attempt_count <= max_attempts" in delivery
    assert "BEFORE UPDATE ON historical_baseline_v2_projector_deliveries" in sql
    assert "BEFORE DELETE ON historical_baseline_v2_projector_deliveries" in sql

    checkpoint = _table_block(sql, "historical_baseline_v2_source_checkpoints")
    for column in (
        "checkpoint_identity",
        "source_domain",
        "source_stream",
        "partition_key",
        "last_source_event_identity",
        "last_source_version",
        "last_projection_sequence",
        "checkpoint_fingerprint",
    ):
        assert _has_column(checkpoint, column)
    assert "UNIQUE KEY uq_hbp_v2_checkpoint_partition" in checkpoint
    assert "BEFORE UPDATE ON historical_baseline_v2_source_checkpoints" in sql
    assert "BEFORE DELETE ON historical_baseline_v2_source_checkpoints" in sql


def test_post_commit_readback_records_exact_or_fail_closed_outcome() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    block = _table_block(sql, "historical_baseline_v2_post_commit_readbacks")
    for column in (
        "readback_identity",
        "projector_receipt_id",
        "delivery_id",
        "projection_sequence",
        "readback_attempt",
        "expected_readback_digest",
        "actual_readback_digest",
        "actual_emitted_occurrence_set_digest",
        "actual_emitted_occurrence_set_count",
        "actual_active_membership_set_digest",
        "actual_active_membership_set_count",
        "actual_state_event_set_digest",
        "actual_successor_set_digest",
        "actual_workflow_event_set_digest",
        "actual_current_alert_fingerprint",
        "readback_result",
        "error_code",
    ):
        assert _has_column(block, column)
    assert "ENUM('exact', 'mismatch', 'unknown')" in block
    assert "REFERENCES historical_baseline_v2_projector_receipts (" in block
    assert "REFERENCES historical_baseline_v2_projector_deliveries(id)" in block
    assert "actual_readback_digest IS NOT NULL" in block
    assert "readback_result IN ('mismatch', 'unknown')" in block
    assert "error_code IS NOT NULL" in block
    assert "BEFORE UPDATE ON historical_baseline_v2_post_commit_readbacks" in sql
    assert "BEFORE DELETE ON historical_baseline_v2_post_commit_readbacks" in sql

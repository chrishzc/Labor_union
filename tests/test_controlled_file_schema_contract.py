"""
File: test_controlled_file_schema_contract.py
Description: 驗證受控檔案 1004 additive release、owned objects、descriptor 與 canonical assembly 契約。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1004_controlled_file_storage_foundation.sql"
MANIFEST_PATH = (
    ROOT
    / "db/migration_releases/labor_union_2026_08_26_controlled_file_storage_foundation_v1.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_26_controlled_file_storage_foundation_v1.descriptors.json"
)
ASSEMBLY_PATH = ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"


def test_controlled_file_release_is_canonical_schema_only_artifact() -> None:
    sql = SQL_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == (
        "labor-union-controlled-file-storage-foundation-2026-08-26-v1"
    )
    assert manifest["artifacts"] == [
        {
            "name": SQL_PATH.name,
            "relative_path": "db/schema_parts/1004_controlled_file_storage_foundation.sql",
            "sha256": hashlib.sha256(sql).hexdigest(),
            "dependencies": [],
            "data_effect": "schema_only",
            "rollback_policy": "code-rollback-preserve-controlled-file-evidence",
            "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
        }
    ]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert descriptor["release_id"] == manifest["release_id"]
    assert set(descriptor["descriptors"][SQL_PATH.name]["tables"]) == {
        "controlled_file_staging_objects",
        "controlled_file_objects",
        "controlled_file_apply_receipts",
        "controlled_file_reconciliation_events",
        "controlled_file_cleanup_events",
    }
    assert assembly["active_bootstrap"][-1] == (
        "db/schema_parts/1004_controlled_file_storage_foundation.sql"
    )

    normalized = load_migration_release_manifest(MANIFEST_PATH, ROOT).owned_object_descriptors(
        ROOT
    )[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)
    assert set(normalized["tables"]) == set(canonical["tables"])
    assert normalized["indexes"] == canonical["indexes"]
    assert normalized["foreign_keys"] == canonical["foreign_keys"]
    assert normalized["checks"] == canonical["checks"]
    assert set(normalized["triggers"]) == set(canonical["triggers"])


def test_controlled_file_schema_keeps_paths_internal_and_events_immutable() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "storage_locator VARCHAR(500) NOT NULL" in sql
    assert "opaque_object_id VARCHAR(64) NOT NULL" in sql
    assert "content_sha256 CHAR(64) NOT NULL" in sql
    assert "preview_fingerprint CHAR(64) NOT NULL" in sql
    assert "schema_version ENUM('controlled-file-apply-receipt.v1') NOT NULL" in sql
    assert "command_type ENUM('controlled_file_apply') NOT NULL" in sql
    assert "cleaned_at_utc DATETIME(6) NULL" in sql
    assert "supersedes_version_number BIGINT UNSIGNED NULL" in sql
    assert "cleanup_id VARCHAR(64) NOT NULL" in sql
    assert "event_id VARCHAR(64) NOT NULL" in sql
    assert "event_sequence TINYINT UNSIGNED NOT NULL" in sql
    assert "event_type ENUM('intent', 'completed', 'reconciliation_required') NOT NULL" in sql
    assert "reason ENUM('expired', 'abandoned') NOT NULL" in sql
    assert "error_code VARCHAR(100) NULL" in sql
    assert "trg_controlled_file_objects_before_update" in sql
    assert "trg_controlled_file_objects_before_delete" in sql
    assert "trg_controlled_file_apply_receipts_before_update" in sql
    assert "trg_controlled_file_apply_receipts_before_delete" in sql
    assert "trg_controlled_file_reconciliation_events_before_update" in sql
    assert "trg_controlled_file_reconciliation_events_before_delete" in sql
    assert "trg_controlled_file_cleanup_events_before_update" in sql
    assert "trg_controlled_file_cleanup_events_before_delete" in sql
    assert "uq_controlled_file_cleanup_sequence" in sql
    assert "uq_controlled_file_cleanup_idempotency_sequence" in sql
    assert "event_sequence = 1 AND event_type = 'intent' AND error_code IS NULL" in sql
    assert "event_sequence = 2 AND event_type = 'completed' AND error_code IS NULL" in sql
    assert "event_type = 'reconciliation_required'" in sql
    assert "CHAR_LENGTH(TRIM(error_code)) > 0" in sql
    assert "ALTER TABLE" not in sql
    assert "object_state" not in sql
    assert "INSERT INTO media_assets" not in sql
    assert "UPDATE media_assets" not in sql

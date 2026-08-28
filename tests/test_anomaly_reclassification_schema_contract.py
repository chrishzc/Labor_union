"""
File: test_anomaly_reclassification_schema_contract.py
Description: 驗證異常必要性移轉 1009 additive schema、release hash 與 owned descriptor。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1009_anomaly_reclassification_disposition.sql"
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_27_anomaly_reclassification_disposition_v1.json"
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_27_anomaly_reclassification_disposition_v1.descriptors.json"
)
ARTIFACT_NAME = SQL_PATH.name
TABLES = {
    "anomaly_reclassification_dispositions",
    "anomaly_reclassification_receipts",
    "anomaly_reclassification_batch_receipts",
}


def test_release_is_schema_only_and_parser_loadable() -> None:
    sql = SQL_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == "labor-union-anomaly-reclassification-disposition-2026-08-27-v1"
    assert manifest["artifacts"] == [{
        "name": ARTIFACT_NAME,
        "relative_path": "db/schema_parts/1009_anomaly_reclassification_disposition.sql",
        "sha256": hashlib.sha256(sql).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": "forward-only-preserve-anomaly-reclassification-evidence",
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert descriptor["release_id"] == manifest["release_id"]
    assert set(descriptor["descriptors"][ARTIFACT_NAME]["tables"]) == TABLES
    loaded = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert loaded.release_id == manifest["release_id"]
    assert loaded.schema_paths(ROOT) == (SQL_PATH.resolve(),)


def test_disposition_contract_is_append_only_and_target_safe() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "disposition ENUM(" in sql
    assert "'reclassified_to_owner_work_item'" in sql
    assert "'retired_false_positive'" in sql
    assert "'replaced_by_successor'" in sql
    assert "FOREIGN KEY (alert_fingerprint)" in sql
    assert "UNIQUE KEY uq_anomaly_reclassification_disposition_alert" in sql
    assert "ON UPDATE RESTRICT ON DELETE RESTRICT" in sql
    assert "target_domain VARCHAR(100) NULL" in sql
    assert "target_reference VARCHAR(191) NULL" in sql
    assert "target_version BIGINT UNSIGNED NULL" in sql
    assert "chk_anomaly_reclassification_disposition_target" in sql
    assert "chk_anomaly_reclassification_disposition_retired_evidence" in sql
    assert "rulebook_reference VARCHAR(500) NULL" in sql
    assert "release_evidence_reference VARCHAR(500) NULL" in sql
    assert "source_identity VARCHAR(191) NOT NULL" in sql
    assert "source_version BIGINT UNSIGNED NOT NULL" in sql
    assert "expected_workflow_version BIGINT UNSIGNED NOT NULL" in sql
    assert "preview_fingerprint CHAR(64) NOT NULL" in sql
    assert "idempotency_key VARCHAR(191) NOT NULL" in sql
    assert "correlation_id VARCHAR(191) NOT NULL" in sql


def test_receipt_and_batch_contracts_are_bound_and_bounded() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "workflow_event_id BIGINT NOT NULL" in sql
    assert "before_state_fingerprint CHAR(64) NOT NULL" in sql
    assert "after_state_fingerprint CHAR(64) NOT NULL" in sql
    assert "before_alert_fingerprint" not in sql
    assert "after_alert_fingerprint" not in sql
    assert "chk_anomaly_reclassification_receipt_versions" in sql
    assert "FOREIGN KEY (workflow_event_id)" in sql
    assert "eligible_codes JSON NOT NULL" in sql
    assert "eligible_codes_fingerprint CHAR(64) NOT NULL" in sql
    assert "cursor_definition_code VARCHAR(191) NOT NULL DEFAULT ''" in sql
    assert "cursor_source_identity VARCHAR(191) NOT NULL DEFAULT ''" in sql
    assert "next_cursor_definition_code VARCHAR(191) NULL" in sql
    assert "next_cursor_source_identity VARCHAR(191) NULL" in sql
    assert "uq_anomaly_reclassification_batch_operation_cursor" in sql
    assert "operation_identity,\n        cursor_definition_code,\n        cursor_source_identity" in sql
    assert "chk_anomaly_reclassification_batch_cursor_pairs" in sql
    assert "operation_identity VARCHAR(191) NOT NULL" in sql
    assert "idempotency_key VARCHAR(191) NOT NULL" in sql
    assert "request_fingerprint CHAR(64) NOT NULL" in sql
    assert "actor VARCHAR(255) NOT NULL" in sql
    assert "correlation_id VARCHAR(191) NOT NULL" in sql
    assert "blocked_items JSON NOT NULL" in sql
    assert "batch_size TINYINT UNSIGNED NOT NULL" in sql
    assert "CHECK (batch_size BETWEEN 1 AND 100)" in sql
    assert "scanned_count INT UNSIGNED NOT NULL" in sql
    assert "applied_count INT UNSIGNED NOT NULL" in sql
    assert "blocked_count INT UNSIGNED NOT NULL" in sql
    assert "before_fingerprints JSON NOT NULL" in sql
    assert "after_fingerprints JSON NOT NULL" in sql
    assert "blocked_items JSON NOT NULL" in sql
    assert "status ENUM('in_progress', 'blocked', 'completed') NOT NULL" in sql
    assert "applied_count + blocked_count = scanned_count" in sql
    assert "status = 'completed' AND next_cursor_definition_code IS NULL" in sql
    assert "status = 'in_progress' AND next_cursor_definition_code IS NOT NULL" in sql


def test_all_owned_tables_reject_update_and_delete() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    for table in TABLES:
        assert f"{table} records cannot be updated" in sql
        assert f"{table} records cannot be deleted" in sql
    assert "ALTER TABLE" not in sql
    assert "INSERT INTO" not in sql

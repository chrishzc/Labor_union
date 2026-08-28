"""
File: test_historical_order_review_remediation_schema_contract.py
Description: 驗證歷史訂單 review 人工更正 1006 schema、descriptor 與 canonical release 連結。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1006_historical_order_review_remediation.sql"
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_26_historical_order_review_remediation_v1.json"
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_26_historical_order_review_remediation_v1.descriptors.json"
)
ASSEMBLY_PATH = ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"
TABLES = {
    "historical_order_review_remediation_events",
    "historical_order_review_remediation_receipts",
    "historical_order_review_remediation_outbox",
}


def test_historical_order_review_remediation_release_is_canonical_schema_only_artifact() -> None:
    sql = SQL_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == "labor-union-historical-order-review-remediation-2026-08-26-v1"
    assert manifest["artifacts"] == [{
        "name": SQL_PATH.name,
        "relative_path": "db/schema_parts/1006_historical_order_review_remediation.sql",
        "sha256": hashlib.sha256(sql).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": "code-rollback-preserve-historical-order-review-remediation-evidence",
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert descriptor["release_id"] == manifest["release_id"]
    assert set(descriptor["descriptors"][SQL_PATH.name]["tables"]) == TABLES
    assert assembly["active_bootstrap"].index(
        "db/schema_parts/1006_historical_order_review_remediation.sql"
    ) < assembly["active_bootstrap"].index(
        "db/schema_parts/1007_finance_recovery_evidence.sql"
    )

    normalized = load_migration_release_manifest(MANIFEST_PATH, ROOT).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)
    assert set(normalized["tables"]) == set(canonical["tables"])
    assert normalized["indexes"] == canonical["indexes"]
    assert normalized["foreign_keys"] == canonical["foreign_keys"]
    assert normalized["checks"] == canonical["checks"]
    assert set(normalized["triggers"]) == set(canonical["triggers"])


def test_historical_order_review_remediation_schema_is_append_only_and_bound_to_prior_review() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "prior_review_identity VARCHAR(191) NOT NULL" in sql
    assert "original_adoption_receipt_id BIGINT UNSIGNED NOT NULL" in sql
    assert "replacement_adoption_receipt_id BIGINT UNSIGNED NOT NULL" in sql
    assert "successor_review_identity VARCHAR(191) NULL" in sql
    assert "UNIQUE KEY uq_historical_order_review_remediation_prior (prior_review_identity)" in sql
    assert "UNIQUE KEY uq_historical_order_review_remediation_replacement" in sql
    assert "expected_remediation_version = 0 AND resulting_remediation_version = 1" in sql
    assert "historical_order_review_remediation_events records cannot be updated" in sql
    assert "historical_order_review_remediation_events records cannot be deleted" in sql
    assert "historical_order_review_remediation_receipts records cannot be updated" in sql
    assert "historical_order_review_remediation_receipts records cannot be deleted" in sql
    assert "ALTER TABLE" not in sql
    assert "INSERT INTO" not in sql

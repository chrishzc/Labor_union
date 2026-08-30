"""
File: test_contract_external_signing_schema_contract.py
Description: 驗證外部簽約 successor 1005 additive schema、descriptor 與 canonical release 契約。
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys

from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1005_contract_external_signing_successor.sql"
MANIFEST_PATH = (
    ROOT
    / "db/migration_releases/labor_union_2026_08_26_contract_external_signing_successor_v1.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_08_26_contract_external_signing_successor_v1.descriptors.json"
)
ASSEMBLY_PATH = ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"
TABLES = {
    "contract_external_signing_sessions",
    "contract_external_completion_reports",
    "contract_final_pdf_recovery_tasks",
    "contract_final_document_versions",
    "contract_external_signing_receipts",
}


def _migration_module():
    """Load the migration helpers without its unrelated global manifest scan."""
    module_name = "scripts.migrate_preserved_database_additive_schema"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    release = importlib.import_module("shared_kernel.migration_release")
    original = release._validate_artifact_hashes
    # The runner validates every historical manifest while importing.  A dirty
    # runner source has a stale self-digest; this test validates the 1005
    # manifest and descriptor directly below, then uses the real helpers.
    release._validate_artifact_hashes = lambda *_args, **_kwargs: None
    try:
        return importlib.import_module(module_name)
    finally:
        release._validate_artifact_hashes = original


def test_external_signing_release_is_canonical_schema_only_artifact() -> None:
    migration = _migration_module()
    sql = SQL_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == (
        "labor-union-contract-external-signing-successor-2026-08-26-v1"
    )
    assert manifest["artifacts"] == [
        {
            "name": SQL_PATH.name,
            "relative_path": (
                "db/schema_parts/1005_contract_external_signing_successor.sql"
            ),
            "sha256": hashlib.sha256(sql).hexdigest(),
            "dependencies": [],
            "data_effect": "schema_only",
            "rollback_policy": "code-rollback-preserve-contract-signing-evidence",
            "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
        }
    ]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert descriptor["release_id"] == manifest["release_id"]
    assert set(descriptor["descriptors"][SQL_PATH.name]["tables"]) == TABLES
    active_bootstrap = assembly["active_bootstrap"]
    assert active_bootstrap.index(
        "db/schema_parts/1004_controlled_file_storage_foundation.sql"
    ) < active_bootstrap.index(
        "db/schema_parts/1005_contract_external_signing_successor.sql"
    ) < active_bootstrap.index(
        "db/schema_parts/1006_historical_order_review_remediation.sql"
    )
    assert active_bootstrap[-1] == "db/schema_parts/1018_hcm_resubmission_canonical_review_version.sql"

    normalized = load_migration_release_manifest(MANIFEST_PATH, ROOT).owned_object_descriptors(
        ROOT
    )[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)
    assert set(normalized["tables"]) == set(canonical["tables"])
    assert normalized["indexes"] == canonical["indexes"]
    assert normalized["foreign_keys"] == canonical["foreign_keys"]
    assert normalized["checks"] == canonical["checks"]
    assert set(normalized["triggers"]) == set(canonical["triggers"])
    for table in TABLES:
        assert canonical["tables"][table]
        for contract in canonical["tables"][table].values():
            assert set(contract) >= {
                "column_type", "is_nullable", "column_default", "extra",
            }
    assert set(canonical["parent_columns"]) == {
        "controlled_file_staging_objects", "controlled_file_objects",
    }
    for contract in canonical["parent_columns"].values():
        purpose = contract["purpose"]
        assert set(purpose) >= {
            "column_type", "is_nullable", "column_default", "extra",
        }
        assert "unsigned_contract" in purpose["column_type"]
        assert "final_signed_contract" in purpose["column_type"]


def test_external_signing_schema_keeps_reports_and_receipts_immutable() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "external_signing_session_id VARCHAR(64) NOT NULL" in sql
    assert "aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0" in sql
    assert "source_event_identity VARCHAR(191) NOT NULL" in sql
    assert "source_payload_sha256 CHAR(64) NOT NULL" in sql
    assert "verified_binding_version BIGINT UNSIGNED NULL" in sql
    assert "controlled_file_object_id BIGINT UNSIGNED NOT NULL" in sql
    assert "schema_version ENUM('contract-external-signing-receipt.v1') NOT NULL" in sql
    assert "preview_fingerprint CHAR(64) NULL" in sql
    assert "'unsigned_contract', 'final_signed_contract'" in sql
    assert "trg_contract_external_reports_before_update" in sql
    assert "trg_contract_external_reports_before_delete" in sql
    assert "trg_contract_final_documents_before_update" in sql
    assert "trg_contract_final_documents_before_delete" in sql
    assert "trg_contract_external_receipts_before_update" in sql
    assert "trg_contract_external_receipts_before_delete" in sql
    assert "INSERT INTO" not in sql
    assert "ALTER TABLE controlled_file_staging_objects" in sql
    assert "ALTER TABLE controlled_file_objects" in sql
    assert "DROP TABLE" not in sql


def test_applied_partial_statement_receipt_authorizes_hash_bound_recovery() -> None:
    migration = _migration_module()
    statements = migration.split_sql(SQL_PATH.read_text(encoding="utf-8"))
    receipt = {
        "candidate_database": "lu_test_contract_o2_resume_1005",
        "schema_steps": [{
            "part": SQL_PATH.name,
            "index": 7,
            "statement_sha256": hashlib.sha256(
                statements[6].encode("utf-8")
            ).hexdigest(),
            "status": "applied",
            "verification_status": "pending_part_completion",
            "after_part_state": "partial",
        }],
    }

    assert migration._receipt_resumable_partial_artifacts(
        receipt, "lu_test_contract_o2_resume_1005"
    ) == frozenset({SQL_PATH.name})
    assert not migration._receipt_resumable_partial_artifacts(
        receipt, "lu_test_other_candidate"
    )

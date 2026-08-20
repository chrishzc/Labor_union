"""
File: test_wp95_hcm_resubmission_schema.py
Description: 驗證 WP95 HCM 重送更正資料庫 release 與 owned-object 契約。
"""

from __future__ import annotations

from pathlib import Path

from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT
    / "db"
    / "migration_releases"
    / "labor_union_2026_08_15_wp95_hcm_resubmission_v1.json"
)


def test_wp95_hcm_resubmission_release_has_complete_immutable_evidence_tables() -> None:
    manifest = load_migration_release_manifest(MANIFEST_PATH, ROOT)

    assert manifest.release_id == "labor-union-wp95-hcm-resubmission-2026-08-15-v1"
    descriptor = manifest.owned_object_descriptors(ROOT)[
        "201_hcm_resubmission_corrections.sql"
    ]
    assert set(descriptor["tables"]) == {
        "case_import_hcm_review_case_bindings",
        "case_import_hcm_correction_events",
        "case_import_hcm_correction_receipts",
        "case_import_hcm_correction_outbox",
    }
    assert descriptor["tables"]["case_import_hcm_correction_events"] >= {
        "prior_occurrence_id",
        "source_event_identity",
        "source_fingerprint",
        "adopted_field_paths",
        "root_before_fingerprint",
        "root_after_fingerprint",
    }
    assert set(descriptor["triggers"]) == {
        "trg_hcm_review_case_bindings_before_update",
        "trg_hcm_review_case_bindings_before_delete",
        "trg_hcm_correction_events_before_update",
        "trg_hcm_correction_events_before_delete",
        "trg_hcm_correction_receipts_before_update",
        "trg_hcm_correction_receipts_before_delete",
    }

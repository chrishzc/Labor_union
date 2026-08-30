"""Static acceptance for the Task 97 1015 -> 1018 release chain."""

from __future__ import annotations

from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[1]
RELEASES = (
    (
        "labor_union_2026_08_30_controlled_file_reference_finalize_leases_v1.json",
        "1015_controlled_file_reference_finalize_leases.sql",
    ),
    (
        "labor_union_2026_08_30_current_anomaly_issues_v1.json",
        "1016_current_anomaly_issues.sql",
    ),
    (
        "labor_union_2026_08_30_client_hcm_correction_versioning_v1.json",
        "1017_client_hcm_correction_versioning.sql",
    ),
    (
        "labor_union_2026_08_30_hcm_resubmission_canonical_review_version_v1.json",
        "1018_hcm_resubmission_canonical_review_version.sql",
    ),
)


def test_task97_releases_are_separate_hash_bound_and_ordered() -> None:
    configured = migration.DEFAULT_RELEASE_MANIFESTS
    positions = tuple(configured.index(manifest_name) for manifest_name, _ in RELEASES)
    assert positions == tuple(range(positions[0], positions[0] + len(RELEASES)))

    assembly_names = tuple(path.name for path in load_schema_assembly().active_artifact_paths)
    assert assembly_names[-4:] == tuple(artifact_name for _, artifact_name in RELEASES)

    for manifest_name, artifact_name in RELEASES:
        manifest_path = ROOT / "db" / "migration_releases" / manifest_name
        manifest = load_migration_release_manifest(manifest_path, ROOT)
        assert manifest.schema_paths(ROOT) == (
            (ROOT / "db" / "schema_parts" / artifact_name).resolve(),
        )
        assert manifest.backfills == ()
        released = manifest.owned_object_descriptors(ROOT)[artifact_name]
        canonical = migration._canonical_artifact_descriptor(artifact_name)
        assert released["tables"] == {
            table: set(columns) for table, columns in canonical["tables"].items()
        }
        for contract_kind in ("indexes", "foreign_keys", "checks"):
            assert released[contract_kind] == canonical[contract_kind]
        assert released["triggers"] == set(canonical["triggers"])


def test_task97_altered_parent_contracts_are_exact_and_bounded() -> None:
    media = migration._canonical_artifact_descriptor(
        "1015_controlled_file_reference_finalize_leases.sql"
    )
    anomaly = migration._canonical_artifact_descriptor("1016_current_anomaly_issues.sql")
    hcm = migration._canonical_artifact_descriptor(
        "1017_client_hcm_correction_versioning.sql"
    )
    hcm_review = migration._canonical_artifact_descriptor(
        "1018_hcm_resubmission_canonical_review_version.sql"
    )

    assert set(media["parent_columns"]) == {
        "scheduling_service_day_log_attachments"
    }
    assert set(media["parent_columns"]["scheduling_service_day_log_attachments"]) == {
        "provider_media_id",
        "controlled_file_object_id",
    }
    assert anomaly["parent_columns"] == {}
    assert set(hcm["parent_columns"]) == {"clients"}
    assert set(hcm["parent_columns"]["clients"]) == {
        "client_hcm_correction_version"
    }
    assert set(hcm_review["parent_columns"]) == {
        "case_import_hcm_correction_events"
    }
    assert set(hcm_review["parent_columns"]["case_import_hcm_correction_events"]) == {
        "prior_occurrence_id",
        "canonical_review_identity",
        "expected_review_version",
        "resulting_review_version",
    }

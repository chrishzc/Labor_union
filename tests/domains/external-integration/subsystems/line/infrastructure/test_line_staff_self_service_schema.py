"""Release and schema contracts for verified LINE staff self-service."""

from pathlib import Path

from shared_kernel.migration_release import load_migration_release_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PART_NAME = "191_line_staff_self_service_identity_flow.sql"


def test_staff_self_service_identity_purpose_is_additive() -> None:
    schema = (PROJECT_ROOT / "db" / "schema_parts" / PART_NAME).read_text(
        encoding="utf-8"
    )

    assert "'customer_binding'" in schema
    assert "'staff_verification'" in schema
    assert "'admin_binding'" in schema
    assert "'staff_self_service'" in schema
    assert "DROP" not in schema.upper()


def test_staff_self_service_release_is_hash_locked() -> None:
    manifest_path = (
        PROJECT_ROOT
        / "db"
        / "migration_releases"
        / "labor_union_2026_08_14_line_staff_self_service_v1.json"
    )

    manifest = load_migration_release_manifest(manifest_path, PROJECT_ROOT)

    assert manifest.release_id == (
        "labor-union-line-staff-self-service-2026-08-14-v1"
    )
    assert [item.artifact.name for item in manifest.schema_artifacts] == [PART_NAME]

from __future__ import annotations

from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
PART_NAME = "1021_task96_owner_contract_successors.sql"
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_31_task96_owner_contract_successors_v1.json"


def test_task96_owner_successor_release_is_hash_bound_and_terminal() -> None:
    manifest = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert manifest.schema_paths(ROOT) == ((ROOT / "db/schema_parts" / PART_NAME).resolve(),)
    assert manifest.backfills == ()
    assert load_schema_assembly().active_artifact_paths[-1].name == PART_NAME

    released = manifest.owned_object_descriptors(ROOT)[PART_NAME]
    canonical = migration._canonical_artifact_descriptor(PART_NAME)
    assert set(released["tables"]) == set(canonical["tables"])
    owned_tables = set(released["tables"])
    for kind in ("indexes", "foreign_keys", "checks"):
        expected = {key: value for key, value in canonical[kind].items() if key[0] in owned_tables}
        assert released[kind] == expected
    assert released["triggers"] == set(canonical["triggers"])


def test_task96_owner_successor_keeps_exact_owner_boundaries() -> None:
    sql = (ROOT / "db/schema_parts" / PART_NAME).read_text(encoding="utf-8")
    required = (
        "client_profile_change_events",
        "case_import_pairing_accepted_lineages",
        "finance_import_source_correction_lineages",
        "payroll_late_obligation_dispositions",
        "government_subsidy_claim_correction_lineages",
        "government_subsidy_recoveries",
    )
    for table in required:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "original_review_identity" in sql
    assert "scheduling_snapshot_identity" in sql
    assert "source_outgoing_bank_fact_identity" in sql
    assert "UPDATE finance_import_batches" not in sql
    assert "UPDATE subsidy_claim_batch_items" not in sql
    assert "UPDATE payroll_late_obligation_dispositions" not in sql
    assert "assignment_id BIGINT NOT NULL" in sql


def test_task96_owner_successor_recognizes_exact_status_predecessor() -> None:
    descriptor = migration._canonical_artifact_descriptor(PART_NAME)
    predecessor = {
        "columns": [{
            "table_name": "client_profile_change_requests",
            "column_name": "status",
            "column_type": (
                "enum('pending','approved','partially_approved','rejected','reverted')"
            ),
            "is_nullable": "NO",
            "column_default": "pending",
            "extra": "",
        }],
        "indexes": [],
        "constraints": [],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }

    assert migration.local_additive_descriptor_state(
        predecessor, descriptor, PART_NAME
    ) == "absent"
    assert migration._release_descriptor_metadata_state(
        predecessor,
        PART_NAME,
        migration.OWNED_OBJECTS[PART_NAME],
    ) == "absent"

    predecessor["columns"][0]["column_type"] = "enum('pending','approved')"
    assert migration.local_additive_descriptor_state(
        predecessor, descriptor, PART_NAME
    ) == "drift"

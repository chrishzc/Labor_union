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
    assert PART_NAME in tuple(path.name for path in load_schema_assembly().active_artifact_paths)

    released = manifest.owned_object_descriptors(ROOT)[PART_NAME]
    canonical = migration._canonical_artifact_descriptor(PART_NAME)
    assert set(released["tables"]) == set(canonical["tables"])
    # Parent-table metadata is part of the Client Profile successor contract;
    # the descriptor contract represents parent columns implicitly in the
    # migration runner's canonical descriptor.
    owned_tables = set(released["tables"]) | {"client_profile_change_requests"}
    for kind in ("indexes", "foreign_keys", "checks"):
        expected = {key: value for key, value in canonical[kind].items() if key[0] in owned_tables}
        assert released[kind] == expected
    assert set(canonical["parent_columns"]) == {
        "clients", "client_profile_change_requests"
    }
    assert "staff_overpayment_recoveries" not in canonical["parent_columns"]
    assert all(
        "staff_overpayment" not in str(value)
        for value in released.values()
    )
    assert released["triggers"] == set(canonical["triggers"])


def test_task96_owner_successor_keeps_exact_owner_boundaries() -> None:
    sql = (ROOT / "db/schema_parts" / PART_NAME).read_text(encoding="utf-8")
    required = (
        "client_profile_change_events",
        "client_profile_change_apply_receipts",
        "client_profile_change_outbox",
    )
    for table in required:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    retired = (
        "case_import_pairing_accepted_lineages",
        "finance_import_source_correction_lineages",
        "payroll_late_obligation_dispositions",
        "government_subsidy_claim_correction_lineages",
        "government_subsidy_recoveries",
    )
    for table in retired:
        assert table not in sql
    assert "client_profile_version" in sql
    assert "client_hcm_correction_version" not in sql
    assert "UPDATE finance_import_batches" not in sql
    assert "UPDATE client_profile_change_requests" not in sql


def test_task96_retired_anomaly_provenance_is_zero_ddl_and_classified() -> None:
    retired_path = ROOT / "db/schema_parts/1022_task96_retired_anomaly_owner_contracts.sql"
    retired_sql = retired_path.read_text(encoding="utf-8")
    assert "Classification: retired historical evidence" in retired_sql
    assert not any(
        token in retired_sql.upper()
        for token in ("CREATE TABLE", "ALTER TABLE", "CREATE TRIGGER", "DROP TABLE")
    )
    assembly = load_schema_assembly()
    raw = __import__("json").loads(
        (ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json").read_text(encoding="utf-8")
    )
    retired_key = "db/schema_parts/1022_task96_retired_anomaly_owner_contracts.sql"
    assert raw["classifications"][retired_key] == "retired"
    assert retired_key not in {path.relative_to(ROOT).as_posix() for path in assembly.active_artifact_paths}
    assert set(raw["retirement_contracts"][retired_key]) == {
        "source_object", "successor", "terminal_schema_evidence", "data_effect",
        "replay", "rollback", "unresolved_policy",
    }


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

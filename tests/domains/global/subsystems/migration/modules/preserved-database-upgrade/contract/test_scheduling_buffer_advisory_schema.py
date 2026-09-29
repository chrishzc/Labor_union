from pathlib import Path
from copy import deepcopy
import json

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.reset_fake_database import split_sql
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1047_scheduling_buffer_advisory.sql"
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_29_scheduling_buffer_advisory_v1.json"


def test_buffer_release_preserves_all_rows_and_full_constraints():
    manifest = load_migration_release_manifest(MANIFEST, ROOT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released["tables"] == {table: set(columns) for table, columns in canonical["tables"].items()}
    for kind in ("indexes", "foreign_keys", "checks", "parent_columns"):
        assert released[kind] == canonical[kind]
    predecessor = migration._canonical_artifact_descriptor("109_scheduling_generations.sql")
    for kind in ("tables", "foreign_keys", "checks"):
        assert canonical[kind] == {
            key: value for key, value in predecessor[kind].items()
            if (key if kind == "tables" else key[0]) in canonical["tables"]
        }
    sql = (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")
    statements = split_sql(sql)
    assert len(statements) == 2
    for statement in statements:
        assert migration._local_classify_statement(statement) == "scheduling_buffer_advisory_index_widen"
    assert canonical["indexes"][("scheduling_effective_occupancy", "PRIMARY")]["columns"] == ("staff_id", "occupancy_date", "occupancy_type")
    assert canonical["indexes"][("scheduling_buffer_days", "uq_scheduling_buffer_staff_date_active")]["non_unique"] == 1


def test_buffer_exception_does_not_authorize_removing_actual_service_guard():
    with pytest.raises(migration.LocalAdditiveBlocked, match="destructive ALTER"):
        migration._local_classify_statement("ALTER TABLE staff_schedule DROP INDEX uq_staff_schedule_effective_date")


def test_buffer_descriptor_accepts_exact_predecessor_and_successor_only():
    fixture = Path(__file__).parent / "fixtures/scheduling_buffer_advisory_predecessor_metadata.json"
    predecessor = json.loads(fixture.read_text(encoding="utf-8"))
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    assert migration.local_additive_descriptor_state(predecessor, descriptor, ARTIFACT) == "absent"
    partial = deepcopy(predecessor)
    index = next(row for row in partial["indexes"] if row["index_name"] == "uq_scheduling_buffer_staff_date_active")
    index["non_unique"] = 1
    assert migration.local_additive_descriptor_state(partial, descriptor, ARTIFACT) == "partial"
    successor = deepcopy(partial)
    primary = next(row for row in successor["indexes"] if row["table_name"] == "scheduling_effective_occupancy" and row["index_name"] == "PRIMARY")
    primary["columns"] = "staff_id,occupancy_date,occupancy_type"
    assert migration.local_additive_descriptor_state(successor, descriptor, ARTIFACT) == "exact"
    for kind, field, wrong in (("columns", "column_type", "varchar(255)"),
                               ("foreign_keys", "delete_rule", "CASCADE"),
                               ("indexes", "columns", "staff_id")):
        drift = deepcopy(successor)
        drift[kind][0][field] = wrong
        assert migration.local_additive_descriptor_state(drift, descriptor, ARTIFACT) == "drift"

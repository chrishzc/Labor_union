"""Only the exact original enum or its ordinal-preserving successor is accepted."""
from copy import deepcopy
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import validate_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1051_candidate_weekly_information.sql"
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_10_14_candidate_weekly_information_v1.json"
OLD = "enum('candidates_added','info_1_sent','info_2_sent','willingness_changed','candidate_selected','candidate_withdrawn')"
NEW = OLD[:-1] + ",'info_3_sent')"

def snapshot(column_type):
    return {"columns": [{"table_name": "caregiver_candidate_contact_events", "column_name": "event_type",
        "column_type": column_type, "is_nullable": "NO", "column_default": None, "extra": ""}],
        "indexes": [], "constraints": [], "key_columns": [], "foreign_keys": [], "triggers": [], "show_create_tables": {}, "views": []}

def test_release_widens_only_the_enum_and_preserves_history():
    manifest = load_migration_release_manifest(MANIFEST, ROOT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released["parent_columns"] == canonical["parent_columns"]
    assert canonical["tables"] == {} and canonical["indexes"] == {} and canonical["foreign_keys"] == {}
    assert canonical["checks"] == {} and canonical["triggers"] == {}
    assert validate_schema_assembly() == []
    assert MANIFEST.name == migration.DEFAULT_RELEASE_MANIFESTS[-1]
    assert (ROOT / "db/schema_parts/232_candidate_weekly_information.sql").read_bytes() == (ROOT / "db/schema_parts" / ARTIFACT).read_bytes()
    statements = migration.split_sql((ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8"))
    assert len(statements) == 1 and migration._local_classify_statement(statements[0]) == "candidate_weekly_information_enum_widen"
    assert migration.local_additive_descriptor_state(snapshot(OLD), canonical, ARTIFACT) == "absent"
    assert migration.local_additive_descriptor_state(snapshot(NEW), canonical, ARTIFACT) == "exact"
    for wrong in (OLD.replace("info_1_sent", "info_3_sent"), NEW.replace("info_1_sent','info_2_sent", "info_2_sent','info_1_sent")):
        assert migration.local_additive_descriptor_state(snapshot(wrong), canonical, ARTIFACT) == "drift"
    drift = deepcopy(snapshot(NEW)); drift["columns"][0]["is_nullable"] = "YES"
    assert migration.local_additive_descriptor_state(drift, canonical, ARTIFACT) == "drift"

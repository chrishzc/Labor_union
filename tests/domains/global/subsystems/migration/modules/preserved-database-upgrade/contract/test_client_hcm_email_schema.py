"""HCM email is additive, nullable and independent of BeClass source values."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import validate_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_10_13_client_hcm_email_v1.json"
ARTIFACT = "1049_client_hcm_email.sql"


def _snapshot(columns):
    return {"columns": columns, "indexes": [], "constraints": [], "key_columns": [],
            "foreign_keys": [], "triggers": [], "show_create_tables": {}, "views": []}


def test_email_release_is_additive_and_in_current_fresh_and_preserve_chain():
    release = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert release["backfills"] == []
    assert release["artifacts"][0]["data_effect"] == "schema_only"
    for item in (release["artifacts"][0], release["descriptor_artifact"]):
        assert hashlib.sha256((ROOT / item["relative_path"]).read_bytes()).hexdigest() == item["sha256"]
    assert validate_schema_assembly() == []
    assert MANIFEST.name in migration.DEFAULT_RELEASE_MANIFESTS
    fresh = (ROOT / "db/schema_parts/230_client_hcm_email.sql").read_text(encoding="utf-8")
    bridge = (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")
    assert fresh == bridge
    statements = migration.split_sql(bridge)
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == "alter_add_only"


def test_email_column_absence_exactness_and_metadata_drift_are_distinct():
    released = load_migration_release_manifest(MANIFEST, ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released["parent_columns"] == canonical["parent_columns"]
    assert canonical["tables"] == {}
    assert canonical["indexes"] == {} and canonical["foreign_keys"] == {}
    assert canonical["checks"] == {} and canonical["triggers"] == {}
    assert migration.local_additive_descriptor_state(_snapshot([]), canonical, ARTIFACT) == "absent"
    exact = _snapshot([{"table_name": "clients", "column_name": "email", "column_type": "varchar(100)",
                        "is_nullable": "YES", "column_default": None, "extra": ""}])
    assert migration.local_additive_descriptor_state(exact, canonical, ARTIFACT) == "exact"
    for field, value in (("column_type", "varchar(50)"), ("is_nullable", "NO"), ("column_default", "")):
        drift = deepcopy(exact)
        drift["columns"][0][field] = value
        assert migration.local_additive_descriptor_state(drift, canonical, ARTIFACT) == "drift"

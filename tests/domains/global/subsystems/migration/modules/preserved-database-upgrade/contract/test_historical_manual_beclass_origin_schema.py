import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_14_historical_manual_beclass_origin_v1.json"
ARTIFACT = "1041_historical_manual_beclass_origin.sql"


def test_manual_beclass_origin_release_is_additive_and_hash_bound():
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifact = raw["artifacts"][0]
    descriptor = raw["descriptor_artifact"]

    assert raw["backfills"] == []
    assert artifact["data_effect"] == "schema_only"
    assert hashlib.sha256((ROOT / artifact["relative_path"]).read_bytes()).hexdigest() == artifact["sha256"]
    assert hashlib.sha256((ROOT / descriptor["relative_path"]).read_bytes()).hexdigest() == descriptor["sha256"]


def test_fresh_and_preserve_schema_share_the_explicit_origin_contract():
    fresh = (ROOT / "db/schema_parts/224_historical_manual_beclass_origin.sql").read_text(encoding="utf-8")
    preserve = (ROOT / "db/schema_parts/1041_historical_manual_beclass_origin.sql").read_text(encoding="utf-8")
    assembly = json.loads((ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json").read_text(encoding="utf-8"))

    assert fresh == preserve
    assert "record_origin ENUM('imported', 'admin_manual')" in fresh
    assert "DEFAULT 'imported'" in fresh
    assert "db/schema_parts/224_historical_manual_beclass_origin.sql" in assembly["active_bootstrap"]
    assert assembly["classifications"]["db/schema_parts/1041_historical_manual_beclass_origin.sql"] == "migration-only"


def test_release_descriptor_matches_the_canonical_column_contract():
    released = load_migration_release_manifest(MANIFEST, ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)

    assert released["parent_columns"] == canonical["parent_columns"]
    assert released["tables"] == canonical["tables"] == {}
    assert released["indexes"] == canonical["indexes"] == {}

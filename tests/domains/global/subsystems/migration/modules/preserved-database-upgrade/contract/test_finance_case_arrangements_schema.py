"""Direct-arrangement release is additive, hash-bound, current and immutable."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[8]

def test_direct_arrangement_release_is_selected_and_hash_bound_without_data_backfill(tmp_path):
    from scripts import migrate_preserved_database_additive_schema as migration
    from scripts.schema_assembly import load_schema_assembly
    from scripts.build_validation_schema_release import verify_release, write_release
    from scripts.verify_validation_schema_manifest import load_manifest
    manifest_path=ROOT/'db/migration_releases/labor_union_2026_11_04_finance_case_arrangements_v1.json'
    data=json.loads(manifest_path.read_text('utf-8'))
    assert data['backfills']==[]
    artifact=data['artifacts'][0]
    assert artifact['data_effect']=='schema_only'
    assert hashlib.sha256((ROOT/artifact['relative_path']).read_bytes()).hexdigest()==artifact['sha256']
    descriptor=data['descriptor_artifact']
    assert hashlib.sha256((ROOT/descriptor['relative_path']).read_bytes()).hexdigest()==descriptor['sha256']
    assert manifest_path.name in migration.DEFAULT_RELEASE_MANIFESTS
    assembly=load_schema_assembly()
    assert any(path.name=='244_finance_case_arrangements.sql' for path in assembly.active_artifact_paths)
    fresh=(ROOT/'db/schema_parts/244_finance_case_arrangements.sql').read_bytes()
    assert fresh==(ROOT/artifact['relative_path']).read_bytes()
    sql=fresh.decode('utf-8')
    assert 'PRIMARY KEY (case_no,version)' in sql and 'UNIQUE KEY uk_finance_arrangement_operation' in sql
    assert 'BEFORE UPDATE' in sql and 'BEFORE DELETE' in sql
    assert not any(command in sql.upper() for command in ('UPDATE ORDERS','DELETE FROM','INSERT INTO','ALTER TABLE'))
    manifest = load_manifest()
    release = write_release(manifest, tmp_path / "validation_schema.sql")
    assert verify_release(manifest, release) == []

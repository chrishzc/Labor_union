"""Only the exact reused-pairing CHECK successor may replace the released guard."""
from copy import deepcopy
from pathlib import Path
import os

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = '1065_historical_order_reused_pairing_check.sql'
MANIFEST = ROOT / 'db/migration_releases/labor_union_2026_11_03_historical_order_reused_pairing_check_v1.json'
KEY = ('historical_order_pairing_evidence', 'chk_historical_order_pairing_assignment_shape')


def snapshot():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    columns = [dict(table_name=KEY[0], column_name=name, **column)
               for name, column in descriptor['parent_columns'][KEY[0]].items()]
    return descriptor, dict(columns=columns, indexes=[], foreign_keys=[], key_columns=[],
        constraints=[dict(table_name=KEY[0], constraint_name=KEY[1], constraint_type='CHECK',
                          enforced='YES', check_clause=descriptor['checks'][KEY])],
        triggers=[], views=[], show_create_tables={})


def test_release_is_hash_bound_schema_only_latest_and_in_fresh_assembly():
    release = load_migration_release_manifest(MANIFEST, ROOT)
    owned = release.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert owned['parent_columns'] == canonical['parent_columns']
    assert owned['checks'][KEY] == migration._normalize_check_contract(canonical['checks'][KEY])
    assert release.backfills == ()
    fresh = ROOT / 'db/schema_parts/243_historical_order_reused_pairing_check.sql'
    assert fresh.read_bytes() == (ROOT / 'db/schema_parts' / ARTIFACT).read_bytes()
    assert fresh in load_schema_assembly().active_artifact_paths
    entries = migration._local_ordered_upgrade_entries()
    canonical_names = [schema.artifact.name for schema in migration.RELEASE_MANIFEST.schema_artifacts]
    assert [entry['artifact']['name'] for entry in entries] == canonical_names[
        canonical_names.index(migration.LOCAL_ADDITIVE_BASELINE_ARTIFACT):
    ]
    selected = [entry for entry in entries if entry['artifact']['name'] == ARTIFACT]
    assert len(selected) == 1
    entry = selected[0]
    schema, = release.schema_artifacts
    assert entry['release_id'] == release.release_id
    assert entry['release_fingerprint'] == release.fingerprint
    assert entry['data_effect'] == schema.data_effect == 'schema_only'
    assert entry['backfill_ids'] == ()
    assert entry['artifact'] == {
        'name': schema.artifact.name,
        'relative_path': schema.artifact.relative_path,
        'sha256': schema.artifact.sha256,
    }
    sql = migration.split_sql(fresh.read_text(encoding='utf-8'))
    assert len(sql) == 1
    assert migration._local_classify_statement(sql[0]) == 'alter_add_only'
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_classify_statement('ALTER TABLE historical_order_pairing_evidence DROP CHECK chk_historical_order_pairing_assignment_shape')
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_classify_statement(sql[0].replace('AND staff_id IS NOT NULL', ''))


def test_pending_exact_partial_drift_and_immutable_predecessor_compatibility():
    descriptor, current = snapshot()
    state = lambda value: migration.local_additive_descriptor_state(value, descriptor, ARTIFACT)
    assert state(current) == 'exact'
    predecessor = migration._canonical_artifact_descriptor('194_historical_order_adoption.sql')['checks'][KEY]
    old = deepcopy(current)
    old['constraints'][0]['check_clause'] = predecessor
    assert state(old) == 'absent'
    released = load_migration_release_manifest(MANIFEST, ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    assert migration._release_descriptor_metadata_state(old, ARTIFACT, released) == 'absent'
    assert migration._release_descriptor_metadata_state(current, ARTIFACT, released) == 'exact'
    assert migration._normalize_check_contract(descriptor['checks'][KEY]) in {
        migration._normalize_check_contract(clause)
        for clause in migration._allowed_later_artifact_checks('194_historical_order_adoption.sql')[KEY]}
    for field, value in [('check_clause', 'assignment_id IS NOT NULL'), ('enforced', 'NO'), ('constraint_type', 'UNIQUE')]:
        drift = deepcopy(current)
        drift['constraints'][0][field] = value
        assert state(drift) == 'drift'
    missing = deepcopy(current)
    missing['constraints'] = []
    assert state(missing) == 'partial'
    missing = deepcopy(current)
    missing['columns'] = []
    assert state(missing) == 'partial'
    drift = deepcopy(current)
    drift['columns'][1]['column_type'] = 'bigint'
    assert state(drift) == 'drift'


@pytest.fixture(scope='module')
def engine_check():
    database = os.environ.get('LU_REUSED_PAIRING_FRESH_DATABASE')
    if not database:
        pytest.skip('explicit fresh MySQL qualification database is required')
    from dotenv import dotenv_values
    import pymysql
    values = dotenv_values(ROOT / '.env')
    assert values.get('APP_ENV') == 'development'
    assert values.get('DB_HOST') in {'127.0.0.1', 'localhost'}
    assert database.startswith('lu_test_reused_pairing_fresh_') and migration.IDENTIFIER.fullmatch(database)
    connection = pymysql.connect(host=values['DB_HOST'], port=int(values.get('DB_PORT', '3306')),
        user=values.get('DB_USERNAME') or values.get('DB_USER'), password=values.get('DB_PASSWORD'), database=database)
    with connection.cursor() as cursor:
        cursor.execute('SELECT check_clause FROM information_schema.check_constraints WHERE constraint_schema=%s AND constraint_name=%s', (database, KEY[1]))
        clause = cursor.fetchone()[0].replace("\\'", "'")
    yield connection, clause
    connection.close()


@pytest.mark.parametrize('resolution,staff_id,assignment_id,expected', [
    ('assignment_candidate', 1, 10, 1), ('assignment_candidate', None, 10, 0),
    ('assignment_candidate', 1, None, 0), ('assignment_candidate', None, None, 0),
    ('assignment_reused', 1, 10, 1), ('assignment_reused', None, 10, 0),
    ('assignment_reused', 1, None, 0), ('assignment_reused', None, None, 0),
    ('evidence_only', 1, None, 1), ('evidence_only', 1, 10, 0),
    ('blank', None, None, 1), ('blank', None, 10, 0),
])
def test_actual_mysql_check_accepts_exactly_the_authorized_reference_shapes(engine_check, resolution, staff_id, assignment_id, expected):
    connection, clause = engine_check
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT ({clause}) FROM (SELECT %s AS resolution, %s AS staff_id, %s AS assignment_id) AS sample',
                       (resolution, staff_id, assignment_id))
        assert cursor.fetchone()[0] == expected

"""Exact metadata and label preservation for the new subsidy-period release."""
from copy import deepcopy
import hashlib,json,os,re
from pathlib import Path
from uuid import uuid4
import pytest
from scripts import migrate_preserved_database_additive_schema as migration
from scripts.migrate_subsidy_period_policy import plan,apply
from shared_kernel.migration_release import load_migration_release_manifest

ROOT=Path(__file__).resolve().parents[8]
ARTIFACT='1055_government_subsidy_periods.sql'
MANIFEST=ROOT/'db/migration_releases/labor_union_2026_10_27_government_subsidy_periods_hash_v2.json'


def test_hash_successor_preserves_sql_descriptors_backfill_and_archived_release():
    old_path = ROOT/'db/migration_releases/labor_union_2026_10_24_government_subsidy_periods_v1.json'
    old = json.loads(old_path.read_text(encoding='utf-8'))
    current = json.loads((ROOT/'db/migration_releases/labor_union_2026_10_27_government_subsidy_periods_hash_v2.json').read_text(encoding='utf-8'))
    old_descriptors = json.loads((ROOT/old['descriptor_artifact']['relative_path']).read_text(encoding='utf-8'))
    current_descriptors = json.loads((ROOT/current['descriptor_artifact']['relative_path']).read_text(encoding='utf-8'))
    assert old['artifacts'][0]['sha256'] == '1d909e243914353cb485bef9475094c1d9ab810772500d94a4b5061a55b86e9b'
    assert old_path.name not in migration.DEFAULT_RELEASE_MANIFESTS
    assert current['source_baseline'] == old['source_baseline']
    assert current['backfills'] == old['backfills']
    assert current_descriptors['descriptors'] == old_descriptors['descriptors']
    assert {k:v for k,v in current['artifacts'][0].items() if k != 'sha256'} == {
        k:v for k,v in old['artifacts'][0].items() if k != 'sha256'
    }
    preserve = migration.split_sql((ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8'))
    fresh = migration.split_sql((ROOT/'db/schema_parts/233_government_subsidy_periods.sql').read_text(encoding='utf-8'))
    assert fresh[:-1] == preserve
    assert fresh[-1].startswith('INSERT IGNORE INTO client_subsidy_policy_migrations')


def metadata(descriptor):
    snapshot={'columns':[],'indexes':[],'constraints':[],'key_columns':[],'foreign_keys':[],'triggers':[],'views':[],'show_create_tables':{}}
    for table,columns in descriptor['tables'].items():
        snapshot['columns'].extend({'table_name':table,'column_name':column,**contract} for column,contract in columns.items())
    for (table,name),contract in descriptor['indexes'].items():
        snapshot['indexes'].append({'table_name':table,'index_name':name,'non_unique':contract['non_unique'],'columns':','.join(contract['columns'])})
    for (table,name),contract in descriptor['checks'].items():
        snapshot['constraints'].append({'table_name':table,'constraint_name':name,'constraint_type':'CHECK','enforced':'YES','check_clause':contract})
    for (table,name),contract in descriptor['foreign_keys'].items():
        snapshot['constraints'].append({'table_name':table,'constraint_name':name,'constraint_type':'FOREIGN KEY'})
        snapshot['foreign_keys'].append({'table_name':table,'constraint_name':name,'update_rule':contract['update_rule'],'delete_rule':contract['delete_rule']})
        for index,(column,parent_column) in enumerate(zip(contract['columns'],contract['referenced_columns']),1):
            snapshot['key_columns'].append({'table_name':table,'constraint_name':name,'column_name':column,
                'ordinal_position':index,'referenced_table_name':contract['referenced_table'],'referenced_column_name':parent_column})
    return snapshot


def test_release_binds_separate_schema_and_backfill_and_fresh_does_not_relabel_current_clients():
    manifest=load_migration_release_manifest(MANIFEST,ROOT)
    released=manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical=migration._canonical_artifact_descriptor(ARTIFACT)
    assert released['tables']=={table:set(columns) for table,columns in canonical['tables'].items()}
    for kind in ('indexes','foreign_keys','checks','parent_columns'):assert released[kind]==canonical[kind]
    raw=json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert raw['artifacts'][0]['data_effect']=='schema_only' and len(raw['backfills'])==1
    for item in (raw['artifacts'][0],raw['descriptor_artifact'],raw['backfills'][0]['artifact']):
        assert hashlib.sha256((ROOT/item['relative_path']).read_bytes()).hexdigest()==item['sha256']
    assert MANIFEST.name in migration.DEFAULT_RELEASE_MANIFESTS
    assert 'subsidy-period-policy-v1' in {item.backfill_id for item in migration.RELEASE_MANIFEST.backfills}
    fresh=(ROOT/'db/schema_parts/233_government_subsidy_periods.sql').read_text(encoding='utf-8')
    assert 'INSERT IGNORE INTO client_subsidy_policy_migrations' in fresh
    assert not re.search(r'\b(?:UPDATE|DELETE)\s+clients\b',fresh,re.I)



def test_exact_descriptor_rejects_partial_column_index_foreign_key_check_and_collation_drift():
    descriptor=migration._canonical_artifact_descriptor(ARTIFACT)
    exact=metadata(descriptor)
    state=lambda snapshot:migration.local_additive_descriptor_state(snapshot,descriptor,ARTIFACT)
    assert state(metadata({'tables':{},'indexes':{},'checks':{},'foreign_keys':{}}))=='absent'
    assert state(exact)=='exact'
    partial=deepcopy(exact)
    missing_table='government_subsidy_period_members'
    for kind in ('columns','indexes','constraints','key_columns','foreign_keys'):
        partial[kind]=[row for row in partial[kind] if row['table_name']!=missing_table]
    assert state(partial)=='partial'
    missing_column=deepcopy(exact);missing_column['columns'].pop()
    assert state(missing_column)=='drift'
    for group,field,wrong in [('columns','column_type','varchar(255)'),('indexes','non_unique',1),
                              ('foreign_keys','delete_rule','CASCADE'),('constraints','check_clause','amount_ntd >= 0')]:
        drift=deepcopy(exact);drift[group][0][field]=wrong
        assert state(drift)=='drift'
    drift=deepcopy(exact)
    next(row for row in drift['columns'] if row['column_name']=='idempotency_key')['collation_name']='utf8mb4_unicode_ci'
    assert state(drift)=='drift'


@pytest.mark.skipif(not os.getenv('SUBSIDY_PERIOD_TEST_DB'),reason='explicit local synthetic database authority required')
def test_actual_fresh_metadata_matches_the_exact_release():
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    assert DB_CONFIG['host'] in {'localhost','127.0.0.1'}
    config=migration.DatabaseConfig(DB_CONFIG['host'],DB_CONFIG['port'],DB_CONFIG['user'],DB_CONFIG['password'])
    snapshot=migration._schema_snapshot(config,os.environ['SUBSIDY_PERIOD_TEST_DB'],owned_part=ARTIFACT)
    assert migration._release_descriptor_metadata_state(snapshot,ARTIFACT,migration.OWNED_OBJECTS[ARTIFACT])=='exact'


@pytest.mark.skipif(not os.getenv('SUBSIDY_PERIOD_TEST_DB'),reason='explicit local synthetic database authority required')
def test_one_time_legacy_labels_preserve_meaning_and_never_relabel_new_citizens_on_replay():
    import pymysql
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    assert DB_CONFIG['host'] in {'localhost','127.0.0.1'}
    database='lu_test_subsidy_labels_'+uuid4().hex[:10]
    assert re.fullmatch(r'lu_test_subsidy_labels_[0-9a-f]+',database)
    settings={**DB_CONFIG,'database':None,'autocommit':True,'cursorclass':pymysql.cursors.DictCursor}
    connection=pymysql.connect(**settings)
    created=False
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');created=True
            cursor.execute(f'USE `{database}`')
            # Minimal empty predecessor parents; no financial or personal data is fabricated.
            cursor.execute('CREATE TABLE clients(id INT PRIMARY KEY,identity_status VARCHAR(100))')
            cursor.execute('CREATE TABLE orders(case_no VARCHAR(50),status VARCHAR(100))')
            cursor.execute('CREATE TABLE client_finance_accounts(case_no VARCHAR(50))')
            cursor.execute('CREATE TABLE finance_import_rows(id BIGINT PRIMARY KEY)')
            for statement in migration.split_sql((ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8')):cursor.execute(statement)
            for index,identity in enumerate(('一般市民','補助市民','低收入戶','中低收入戶'),1):
                cursor.execute('INSERT INTO clients VALUES (%s,%s)',(index,identity))
        changes=plan(connection)
        assert [row['after_identity'] for row in changes]==['補助市民','社福','社福','社福']
        apply(connection,changes)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients VALUES (5,'補助市民')")
        assert plan(connection)==[]
        apply(connection,[])
        with connection.cursor() as cursor:
            cursor.execute('SELECT identity_status FROM clients ORDER BY id')
            assert [row['identity_status'] for row in cursor.fetchall()]==['補助市民','社福','社福','社福','補助市民']
            cursor.execute('SELECT COUNT(*) n FROM client_subsidy_identity_label_changes')
            assert cursor.fetchone()['n']==4
    finally:
        if created:
            with connection.cursor() as cursor:cursor.execute(f'DROP DATABASE `{database}`')
        connection.close()

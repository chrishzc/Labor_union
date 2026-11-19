"""Receipt-scoped LINE attempt retention preserves registry guards and rejects drift."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import os
from uuid import uuid4
import pytest
from scripts import migrate_preserved_database_additive_schema as m
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ARTIFACT='1079_line_delivery_retention_guards.sql'
NAME='trg_line_delivery_attempt_events_before_delete'
MANIFEST=m.ROOT/'db/migration_releases/labor_union_2026_11_18_line_delivery_retention_v1.json'

def snapshot(kind):
    contract=m._line_delivery_retention_guard_metadata()[kind][NAME]
    return {'triggers':[{'trigger_name':NAME,**contract}]}

def test_retention_guard_is_registered_and_preserve_fresh_share_one_artifact():
    assert m._local_ordered_upgrade_entries()[-1]['artifact']['name']==ARTIFACT
    assert load_schema_assembly().active_artifact_paths[-1].name==ARTIFACT
    released=load_migration_release_manifest(MANIFEST,m.ROOT).owned_object_descriptors(m.ROOT)[ARTIFACT]
    canonical=m._canonical_artifact_descriptor(ARTIFACT)
    assert released['triggers']==set(canonical['triggers'])
    assert canonical['triggers']==m._line_delivery_retention_guard_metadata()['successor_triggers']
    statements=m.split_sql((m.ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8'))
    assert len(statements)==2
    assert {m._local_classify_statement(s) for s in statements}=={'drop_trigger_if_exists','create_trigger'}

def test_retention_guard_exact_predecessor_missing_and_unknown_states():
    assert m._registry_guard_snapshot(snapshot('predecessor_triggers'),ARTIFACT)[1]=='absent'
    after=snapshot('successor_triggers')
    assert m._registry_guard_snapshot(after,ARTIFACT)[1]=='exact'
    assert m._registry_guard_snapshot({'triggers':[]},ARTIFACT)[1]=='partial'
    changed=deepcopy(after);changed['triggers'][0]['action_statement']+=' unsafe'
    assert m._registry_guard_snapshot(changed,ARTIFACT)[1]=='drift'

def test_successor_normalizes_only_its_exact_guard_and_does_not_change_evidence():
    after=snapshot('successor_triggers');saved=deepcopy(after)
    normalized,state=m._line_delivery_retention_guard_snapshot(after,'154_line_integration_inbox_delivery.sql')
    assert state is None and after==saved
    assert normalized==snapshot('predecessor_triggers')
    normalized,_=m._registry_guard_snapshot(after,'154_line_integration_inbox_delivery.sql')
    assert normalized['triggers'][0]['action_statement']==m._registry_guard_metadata()['predecessor_triggers'][NAME]['action_statement']
    changed=deepcopy(after);changed['triggers'][0]['action_statement']+=' unsafe'
    assert m._line_delivery_retention_guard_snapshot(changed,'154_line_integration_inbox_delivery.sql')[0]==changed

@pytest.mark.skipif(os.getenv('LINE_RETENTION_MYSQL_TEST')!='1',reason='explicit local disposable MySQL opt-in')
def test_mysql_retention_guard_requires_exact_receipt_terminal_old_task_and_no_lease():
    import pymysql
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    base={k:v for k,v in DB_CONFIG.items() if k!='database'}
    base['cursorclass']=pymysql.cursors.Cursor
    assert base.get('host') in {'localhost','127.0.0.1'}
    name='lu_test_retention_guard_'+uuid4().hex
    connection=pymysql.connect(**base,autocommit=True)
    created=False
    try:
        with connection.cursor() as c:
            c.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');created=True
            c.execute(f'USE `{name}`')
            statements=[
                'CREATE TABLE line_delivery_tasks (id BIGINT PRIMARY KEY, processing_status VARCHAR(32), updated_at_utc DATETIME(6), lease_owner VARCHAR(191), lease_acquired_at_utc DATETIME(6), lease_expires_at_utc DATETIME(6), source_aggregate_identity VARCHAR(191),source_aggregate_type VARCHAR(191))',
                'CREATE TABLE line_delivery_attempt_events (id BIGINT PRIMARY KEY, task_id BIGINT,completed_at_utc DATETIME(6))',
                'CREATE TABLE line_command_receipts (idempotency_key VARCHAR(191),result_reference VARCHAR(191),result_snapshot JSON)',
                'CREATE TABLE application_command_claims (idempotency_key VARCHAR(191) COLLATE utf8mb4_bin,command_family VARCHAR(100),aggregate_identity VARCHAR(191) COLLATE utf8mb4_bin)',
                'CREATE TABLE admin_command_receipts (idempotency_key VARCHAR(191) COLLATE utf8mb4_bin,command_family VARCHAR(100))',
                'CREATE TABLE contract_signing_events (case_no VARCHAR(191),event_type VARCHAR(100))',
                'CREATE TABLE order_contract_flow_events (case_no VARCHAR(191),event_type VARCHAR(100))']
            for sql in statements:c.execute(sql)
            for sql in m.split_sql((m.ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8')):c.execute(sql)
            c.execute('SELECT TRIGGER_NAME AS trigger_name,ACTION_TIMING AS action_timing,EVENT_MANIPULATION AS event_manipulation,EVENT_OBJECT_TABLE AS event_object_table,ACTION_STATEMENT AS action_statement FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME=%s',(name,NAME))
            trigger=dict(zip((column[0] for column in c.description),c.fetchone()))
            assert m._registry_guard_snapshot({'triggers':[trigger]},ARTIFACT)[1]=='exact'
            c.execute("SELECT CONVERT_TZ(DATE_SUB(CONVERT_TZ(UTC_TIMESTAMP(6),'+00:00','+08:00'), INTERVAL 6 MONTH),'+08:00','+00:00'), UTC_TIMESTAMP(6)")
            cutoff_at,recent=c.fetchone()
            cutoff=cutoff_at.strftime('%Y-%m-%d %H:%M:%S.%f')
            old=cutoff_at-timedelta(days=1)
            for identity,status,updated,lease in [(1,'sent',old,None),(2,'pending',old,None),(3,'cancelled',recent,None),(4,'sent',old,'busy'),(5,'cancelled',old,None),(6,'sent',old,None)]:
                c.execute('INSERT INTO line_delivery_tasks VALUES (%s,%s,%s,%s,NULL,NULL,%s,%s)',(identity,status,updated,lease,'SYNTH-CASE','orders'))
                c.execute('INSERT INTO line_delivery_attempt_events VALUES (%s,%s,%s)',(identity,identity,old if identity!=6 else recent))
            def proof(identity,**patch):
                data={'task_id':identity,'cutoff':cutoff,**patch}
                c.execute('DELETE FROM line_command_receipts')
                c.execute('INSERT INTO line_command_receipts VALUES (%s,%s,%s)',('retention-key','line-delivery-retention:'+str(identity),json.dumps(data)))
                c.execute('SET @line_delivery_retention_key=%s',('retention-key',))
            for identity in (1,2,3,4,6):
                if identity!=1:proof(identity)
                with pytest.raises(pymysql.MySQLError):c.execute('DELETE FROM line_delivery_attempt_events WHERE id=%s',(identity,))
            proof(1,task_id=99)
            with pytest.raises(pymysql.MySQLError):c.execute('DELETE FROM line_delivery_attempt_events WHERE id=1')
            proof(3,cutoff='2099-01-01 00:00:00.000000')
            with pytest.raises(pymysql.MySQLError):c.execute('DELETE FROM line_delivery_attempt_events WHERE id=3')
            proof(1);c.execute('DELETE FROM line_delivery_attempt_events WHERE id=1');assert c.rowcount==1
            # Original registry deletion branch remains independently valid.
            c.execute('SET @line_delivery_retention_key=NULL,@registry_delete_key=%s,@registry_delete_case=%s,@registry_delete_tasks=JSON_ARRAY()',('registry-key','SYNTH-CASE'))
            c.execute('INSERT INTO application_command_claims VALUES (%s,%s,%s)',('registry-key','registry_delete/v1','case:SYNTH-CASE'))
            c.execute('DELETE FROM line_delivery_attempt_events WHERE id=5');assert c.rowcount==1
    finally:
        if created:
            with connection.cursor() as c:c.execute(f'DROP DATABASE `{name}`')
        connection.close()

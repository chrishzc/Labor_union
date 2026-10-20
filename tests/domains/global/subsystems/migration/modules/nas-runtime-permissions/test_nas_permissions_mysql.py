"""Opt-in real MySQL oracles; only a previously owned isolated qualification DB.

NAS_PERMISSION_TEST_SETTINGS names an ignored JSON file with connection file
paths and an owned lu_test_nas_security_* database. No application .env is read.
Fixtures remain in that disposable database for diagnosis; no reset/drop occurs.
"""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import pymysql
import pytest

from infrastructure.mysql.nas_mutations import PROCEDURES, RELATIONS, call_mutation
from infrastructure.mysql.nas_permissions import PROFILES, account_names, permission_plan, verify_runtime_permissions


@pytest.fixture(scope='module')
def engine():
    path = os.environ.get('NAS_PERMISSION_TEST_SETTINGS')
    if not path:
        pytest.skip('explicit isolated MySQL settings required')
    settings = json.loads(Path(path).read_text(encoding='utf-8'))
    assert settings['host'] == '127.0.0.1' and settings['port'] == 43319
    assert re.fullmatch(r'lu_test_nas_security_[0-9a-f]{12}', settings['database'])
    assert settings['owned_disposable'] is True
    return settings


@contextmanager
def connect(engine, profile='root', *, tls=True):
    options = dict(host=engine['host'], port=engine['port'], database=engine['database'],
        user='root' if profile == 'root' else account_names(engine['database'])[profile],
        password=Path(engine['password_files'][profile]).read_text(encoding='utf-8').strip(),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False,
        connect_timeout=5, read_timeout=20, write_timeout=20)
    if tls:
        options['ssl'] = {'ca': engine['ca_file'], 'check_hostname': True}
    else:
        # Current PyMySQL prefers TLS even without explicit SSL arguments.
        options['ssl_disabled'] = True
    connection = pymysql.connect(**options)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def execute(connection, sql, args=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, args or None)
        return cursor.lastrowid


def scalar(connection, sql, args=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return next(iter(cursor.fetchone().values()))


def call(connection, name, args):
    with connection.cursor() as cursor:
        call_mutation(cursor, name, *args)


def denied(connection, sql, args=(), *, numbers=(1142, 1143, 1227, 1370)):
    with pytest.raises(pymysql.MySQLError) as failure:
        execute(connection, sql, args)
    assert failure.value.args[0] in numbers
    connection.rollback()


def test_public_line_cannot_write_private_photo_or_log_facts(engine):
    from infrastructure.mysql.nas_permissions import LINE_PRIVATE_PHOTO_TABLES
    with connect(engine, 'line') as public:
        for table in sorted(LINE_PRIVATE_PHOTO_TABLES):
            assert scalar(public, f'SELECT COUNT(*) FROM `{table}`') >= 0
            denied(public, f'INSERT INTO `{table}` () VALUES ()')
    with connect(engine, 'management') as owner:
        with owner.cursor() as cursor:
            cursor.execute('SHOW GRANTS')
            grants = '\n'.join(str(next(iter(row.values()))) for row in cursor.fetchall())
        for table in LINE_PRIVATE_PHOTO_TABLES:
            assert any('INSERT' in grant and f'`{table}`' in grant for grant in grants.splitlines())


@pytest.mark.parametrize('profile', PROFILES)
def test_exact_grants_tls_and_direct_destructive_operations_rejected(engine, profile):
    with connect(engine) as admin:
        plan = permission_plan(admin, engine['database'])
    with connect(engine, profile) as runtime:
        verify_runtime_permissions(runtime, profile, engine['database'],
            expected_tables=plan['tables'], expected_views=plan['views'])
        assert scalar(runtime, "SELECT @@port") == 3306
        with runtime.cursor() as cursor:
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            assert cursor.fetchone()['Value']
        for sql in ('DELETE FROM clients WHERE id=-1', 'DELETE FROM holidays WHERE holiday_date=\'1900-01-01\'',
                    'ALTER TABLE clients ADD COLUMN forbidden_test INT',
                    'CREATE TABLE forbidden_test (id INT)',
                    "CREATE USER 'forbidden_test'@'%' ACCOUNT LOCK",
                    'TRUNCATE TABLE holidays',
                    f"GRANT SELECT ON clients TO '{account_names(engine['database'])[profile]}'@'%'"):
            denied(runtime, sql)
    with pytest.raises(pymysql.MySQLError) as failure:
        with connect(engine, profile, tls=False):
            pytest.fail('REQUIRE SSL account accepted plaintext')
    assert failure.value.args[0] == 1045


def test_line_cannot_write_core_approve_or_read_account_secrets(engine):
    with connect(engine, 'line') as line:
        for sql in ("INSERT INTO clients(name) VALUES('forbidden')",
                    'UPDATE orders SET service_days=service_days WHERE case_no=\'absent\'',
                    'UPDATE client_payments SET id=id WHERE id=-1',
                    'UPDATE provisional_client_registrations SET approved_by_actor=\'forbidden\' WHERE id=-1',
                    'SELECT password_hash FROM admin_users',
                    "CALL lu_nas_delete_holiday_v1('1900-01-01')"):
            denied(line, sql)
        # Read-only parent facts can still be locked without a core UPDATE grant.
        execute(line, 'SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE', ('absent',))
        line.rollback()


@pytest.mark.parametrize('name', sorted(PROCEDURES))
def test_each_procedure_executes_with_allowed_profile_and_outer_rollback(engine, name):
    """A valid mutation changes exactly its scoped rows; rollback restores them."""
    profile = PROCEDURES[name][2][0]
    with connect(engine) as admin:
        args, probe, before, after = seed_operation(admin, name)
        admin.commit()
    with connect(engine, profile) as runtime:
        assert scalar(runtime, *probe) == before
        call(runtime, name, args)
        assert scalar(runtime, *probe) == after
        runtime.rollback()
        assert scalar(runtime, *probe) == before
        runtime.rollback()
        call(runtime, name, args)
        runtime.commit()
        assert scalar(runtime, *probe) == after
    with connect(engine) as admin:
        assert scalar(admin, *probe) == after


def seed_operation(admin, name):
    key = uuid4().hex
    staff = execute(admin, "INSERT INTO staff(name) VALUES(%s)", ('nas-test-'+key,))
    if name == 'lu_nas_delete_holiday_v1':
        # One operation per run; far-future scenario dates are not canonical seeds.
        date = f'{3000 + int(key[:3],16):04d}-01-01'
        execute(admin, 'INSERT INTO holidays(holiday_date,holiday_name) VALUES(%s,%s)', (date,key))
        return (date,), ('SELECT COUNT(*) FROM holidays WHERE holiday_date=%s',(date,)), 1, 0
    for table, (column, detail) in RELATIONS.items():
        if name in {f'lu_nas_remove_{table}_v1', f'lu_nas_replace_{table}_v1'}:
            columns = [column] + ([detail] if detail else [])
            values = ['test'] + (['detail'] if detail else [])
            execute(admin, f"INSERT INTO `{table}`(staff_id,{','.join('`'+c+'`' for c in columns)}) VALUES ({','.join(['%s']*(len(values)+1))})", (staff,*values))
            args = (staff, 'test', 'detail') if '_remove_' in name else (staff,json.dumps([dict(zip(columns,values))]))
            return args, (f'SELECT COUNT(*) FROM `{table}` WHERE staff_id=%s',(staff,)),1,0
    if name == 'lu_nas_replace_staff_banks_v1':
        # Synthetic fixture token, never a real bank account.
        account = 'fixture-'+key
        execute(admin, 'INSERT INTO staff_bank_accounts(staff_id,bank_code,branch_code,account_no) VALUES(%s,%s,%s,%s)',
                (staff,'000','0000',account))
        expected = json.dumps([dict(bank_code='000',branch_code='0000',account_no=account,is_primary=1)])
        return (staff,expected), ('SELECT COUNT(*) FROM staff_bank_accounts WHERE staff_id=%s',(staff,)),1,0
    if name == 'lu_nas_trim_preferences_v1':
        definition = execute(admin, "INSERT INTO staff_matching_preference_definitions(preference_key,display_name,value_kind,comparison_operator,created_by,updated_by) VALUES(%s,'test','integer_set','contains_integer','test','test')",(key,))
        execute(admin, "INSERT INTO staff_matching_preference_profiles(staff_id,version,created_by,updated_by) VALUES(%s,1,'test','test')",(staff,))
        execute(admin, "INSERT INTO staff_matching_preference_values(staff_id,definition_id,value_json,profile_version,updated_by) VALUES(%s,%s,'{}',1,'test')",(staff,definition))
        return (staff,1,'[]'), ('SELECT COUNT(*) FROM staff_matching_preference_values WHERE staff_id=%s',(staff,)),1,0
    if name in {'lu_nas_replace_case_account_v1','lu_nas_cancel_occupancy_v1'}:
        case = 'nas-'+key
        client = execute(admin,'INSERT INTO clients(name,case_no) VALUES(%s,%s)',('test',case))
        execute(admin,'INSERT INTO orders(case_no,client_id) VALUES(%s,%s)',(case,client))
        if 'case_account' in name:
            old_account = f'99781699{staff*2:06d}'
            new_account = f'99781699{staff*2+1:06d}'
            old = execute(admin,"INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES(%s,%s,%s,2,'test')",(case,old_account,'a'*64))
            return (case,json.dumps([old]),new_account,'b'*64,'test'), ("SELECT COUNT(*) FROM client_legacy_virtual_accounts WHERE case_no=%s AND virtual_account=%s",(case,old_account)),1,0
        generation = execute(admin,"INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) VALUES(%s,1,1,'effective',1,'test','test')",(case,))
        assignment = execute(admin,'INSERT INTO case_staff_assignments(case_no,generation_id,staff_id,assignment_sequence) VALUES(%s,%s,%s,1)',(case,generation,staff))
        execute(admin,"INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) VALUES(%s,'2030-01-01',%s,%s,'assignment_interval')",(staff,generation,assignment))
        return (case,generation), ('SELECT COUNT(*) FROM scheduling_effective_occupancy WHERE generation_id=%s',(generation,)),1,0
    if name == 'lu_nas_remove_current_issue_v1':
        issue = 'ci_'+key*2
        execute(admin,"INSERT INTO current_anomaly_issues(issue_key,definition_code,owner_domain,owner_root_type,subject_type,subject_id,subject_identity,owner_snapshot_token,owner_version,severity,blocking,details,episode_started_at,last_verified_at) VALUES(%s,'test','test','test','test','test','{}','test',1,'warning',0,'{}',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",(issue,))
        return (issue,'test','test','test'), ('SELECT COUNT(*) FROM current_anomaly_issues WHERE issue_key=%s',(issue,)),1,0
    if name == 'lu_nas_archive_audits_v1':
        audit = execute(admin,"INSERT INTO admin_audit_logs(action,created_at,details_json) VALUES('test','2020-01-01','{}')")
        return (json.dumps([audit]),), ('SELECT COUNT(*) FROM admin_audit_logs WHERE id=%s',(audit,)),1,0
    occurred = datetime(2020,1,1)
    if name == 'lu_nas_purge_knowledge_request_v1':
        request = execute(admin,"INSERT INTO knowledge_answer_requests(question,request_status,idempotency_key,correlation_id,created_at_utc) VALUES('test','answered',%s,%s,%s)",(key,key,occurred))
        receipt = execute(admin,"INSERT INTO knowledge_answer_receipts(answer_request_id,answer_text,index_version) VALUES(%s,'test',1)",(request,))
        source = execute(admin,"INSERT INTO knowledge_answer_sources(answer_receipt_id,source_identity,source_version,safe_excerpt,citation_order) VALUES(%s,'test',1,'test',1)",(receipt,))
        job = execute(admin,"INSERT INTO knowledge_jobs(job_type,answer_request_id,idempotency_key,created_by_actor_id) VALUES('answer',%s,%s,'test')",(request,key))
        return (request,'answered',occurred,receipt,source,job), ('SELECT COUNT(*) FROM knowledge_answer_requests WHERE id=%s',(request,)),1,0
    if name == 'lu_nas_purge_knowledge_job_v1':
        job = execute(admin,"INSERT INTO knowledge_jobs(job_type,processing_status,idempotency_key,created_by_actor_id,created_at_utc) VALUES('index_build','completed',%s,'test',%s)",(key,occurred))
        return (job,'completed',occurred,0), ('SELECT COUNT(*) FROM knowledge_jobs WHERE id=%s',(job,)),1,0
    if name == 'lu_nas_purge_knowledge_index_v1':
        version = int(key[:7],16)+100
        execute(admin,"INSERT INTO knowledge_indexes(index_version,index_status,created_at_utc) VALUES(%s,'failed',%s)",(version,occurred))
        return (version,'failed',occurred), ('SELECT COUNT(*) FROM knowledge_indexes WHERE index_version=%s',(version,)),1,0
    raise AssertionError(name)


@pytest.mark.parametrize('name', sorted(set(PROCEDURES)-{'lu_nas_delete_holiday_v1'}))
def test_stale_arguments_rejected_and_unrelated_work_stays_in_outer_transaction(engine, name):
    with connect(engine) as admin:
        args, probe, before, _ = seed_operation(admin,name)
        admin.commit()
    bad = list(args)
    if '_remove_staff_' in name: bad[1] = 'absent'
    elif '_replace_staff_' in name: bad[1] = '[]'
    elif name == 'lu_nas_trim_preferences_v1': bad[1] += 1
    elif name == 'lu_nas_replace_case_account_v1': bad[1] = '[]'
    elif name == 'lu_nas_cancel_occupancy_v1': bad[0] = 'another-case'
    elif name == 'lu_nas_remove_current_issue_v1': bad[3] = 'stale'
    elif name == 'lu_nas_archive_audits_v1':
        with connect(engine) as admin:
            recent = execute(admin,"INSERT INTO admin_audit_logs(action) VALUES('test-recent')")
            admin.commit()
        bad[0] = json.dumps([recent])
    elif name == 'lu_nas_purge_knowledge_request_v1': bad[3] += 1
    elif name == 'lu_nas_purge_knowledge_job_v1': bad[3] += 1
    elif name == 'lu_nas_purge_knowledge_index_v1': bad[1] = 'building'
    else: raise AssertionError(name)
    with connect(engine,PROCEDURES[name][2][0]) as runtime:
        execute(runtime,"INSERT INTO admin_audit_logs(action) VALUES('rollback-marker')")
        marker = scalar(runtime,'SELECT LAST_INSERT_ID()')
        with pytest.raises(pymysql.MySQLError) as failure:
            call(runtime,name,bad)
        assert failure.value.args[0] == 1644
        runtime.rollback()
        assert scalar(runtime,*probe) == before
        assert scalar(runtime,'SELECT COUNT(*) FROM admin_audit_logs WHERE id=%s',(marker,)) == 0


@pytest.mark.parametrize('profile', PROFILES)
def test_disallowed_procedures_are_rejected_before_body_execution(engine, profile):
    with connect(engine,profile) as runtime:
        for name,(signature,_,allowed) in PROCEDURES.items():
            if profile in allowed:
                continue
            denied(runtime,f"CALL `{name}`({','.join(['NULL']*len(signature.split(',')))})",numbers=(1370,))


def test_line_intake_approval_replay_and_approval_rollback_use_real_profiles(engine):
    from domains.case_import.provisional_registration import ProvisionalRegistrationIntent, build_provisional_registration_candidate
    from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationConflictError
    key='U-test-'+uuid4().hex
    intent=ProvisionalRegistrationIntent(line_user_id=key,name='synthetic test',phone='0900000000',
        expected_date='2030-01-01',service_days=1,address='synthetic fixture',gender=None,email=None,
        birth_date=None,tel=None,ext=None,city=None,zip_code=None,id_number=None,
        liff_config_revision=None,survey_details={})
    candidate=build_provisional_registration_candidate(intent)
    with connect(engine,'line') as line:
        repo=MySqlProvisionalRegistrationRepository(line)
        submitted=repo.apply(candidate)
        assert submitted.client_id is None and submitted.beclass_record_id is None
        line.commit()
        assert scalar(line,'SELECT COUNT(*) FROM clients WHERE line_user_id=%s',(key,))==0
        replay=repo.apply(candidate)
        assert replay.registration_id==submitted.registration_id
        line.rollback()
    with connect(engine,'management') as manager:
        repo=MySqlProvisionalRegistrationRepository(manager)
        with pytest.raises(ProvisionalRegistrationConflictError):
            repo.approve(submitted.registration_id,99,'test-manager')
        manager.rollback()
        approved=repo.approve(submitted.registration_id,1,'test-manager')
        assert approved.client_id and approved.beclass_record_id
        manager.rollback()
        assert scalar(manager,'SELECT COUNT(*) FROM clients WHERE line_user_id=%s',(key,))==0
        manager.rollback()
        approved=repo.approve(submitted.registration_id,1,'test-manager')
        manager.commit()
        again=repo.approve(submitted.registration_id,1,'test-manager')
        assert again.client_id==approved.client_id and again.beclass_record_id==approved.beclass_record_id
        assert scalar(manager,'SELECT COUNT(*) FROM clients WHERE line_user_id=%s',(key,))==1


def test_parent_lock_is_held_until_outer_rollback(engine):
    with connect(engine) as admin:
        staff=execute(admin,"INSERT INTO staff(name) VALUES('synthetic lock fixture')")
        admin.commit()
    with connect(engine,'management') as first, connect(engine,'management') as second:
        execute(first,'SELECT id FROM staff WHERE id=%s FOR UPDATE',(staff,))
        execute(second,'SET SESSION innodb_lock_wait_timeout=1')
        with pytest.raises(pymysql.MySQLError) as conflict:
            execute(second,'SELECT id FROM staff WHERE id=%s FOR UPDATE',(staff,))
        assert conflict.value.args[0]==1205
        second.rollback()
        first.rollback()
        execute(second,'SELECT id FROM staff WHERE id=%s FOR UPDATE',(staff,))


def test_request_child_snapshot_nulls_and_active_index_are_rejected(engine):
    with connect(engine) as admin:
        args,probe,before,_=seed_operation(admin,'lu_nas_purge_knowledge_request_v1')
        version=scalar(admin,'SELECT COALESCE(MAX(index_version),0)+1 FROM knowledge_indexes')
        execute(admin,"INSERT INTO knowledge_indexes(index_version,index_status,created_at_utc) VALUES(%s,'ready','2020-01-01')",(version,))
        admin.commit()
    with connect(engine,'maintenance') as runtime:
        for offset in (3,4,5):
            bad=list(args);bad[offset]=None
            with pytest.raises(pymysql.MySQLError) as failure:
                call(runtime,'lu_nas_purge_knowledge_request_v1',bad)
            assert failure.value.args[0]==1644
            runtime.rollback()
            assert scalar(runtime,*probe)==before
            runtime.rollback()
        with pytest.raises(pymysql.MySQLError) as failure:
            call(runtime,'lu_nas_purge_knowledge_index_v1',(version,'ready',datetime(2020,1,1)))
        assert failure.value.args[0]==1644
        runtime.rollback()
        assert scalar(runtime,'SELECT COUNT(*) FROM knowledge_indexes WHERE index_version=%s',(version,))==1

"""Real localhost MySQL/API service starts. Signed documents/group identities are synthetic prerequisites.

Every service result, candidate inquiry, willingness response, invitation and date save
uses its actual application/API. No provider or application lifespan worker is run.
"""
import json
import os
import runpy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.mysql import mysql_adapter

DATABASE=os.getenv('SERVICE_START_TEST_DB')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicit disposable localhost service-start DB')
h=runpy.run_path('tests/domains/scheduling/subsystems/scheduling/integration/test_complex_service_accounting_mysql.py')


@pytest.fixture(scope='module')
def http():
    assert DATABASE.startswith('lu_test_') and mysql_adapter.DB_CONFIG['host'] in ('127.0.0.1','localhost')
    from api.dependencies import admin_auth
    from api.routes import (
        finance_import, line_mobile_admin, line_staff_self_service, official_service_date_correction,
        order_intake_terms_bootstrap, service_start, staff_leave_intake,
    )
    from api.dependencies import line_identity
    from domains.line.identities import LineUserId
    from subsystems.access.authentication_session import AdminPrincipal
    from infrastructure.mysql.nas_mutations import PROCEDURES
    app=FastAPI()
    for module in (
        service_start, line_staff_self_service, line_mobile_admin, order_intake_terms_bootstrap, finance_import,
        staff_leave_intake, official_service_date_correction,
    ):
        app.include_router(module.router)
    principal=AdminPrincipal(1,'synthetic-union','測試工會人員','system_admin')
    for guard in [admin_auth.require_admin,admin_auth.require_system_admin,admin_auth.require_persisted_admin,admin_auth.require_line_matching_override]:
        app.dependency_overrides[guard]=lambda:principal
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG,'database',DATABASE)
        verifier=SimpleNamespace(verify=lambda token:SimpleNamespace(line_user_id=LineUserId(token)))
        patch.setattr(line_staff_self_service,'get_liff_token_verifier',lambda:verifier)
        patch.setattr(line_mobile_admin,'get_liff_token_verifier',lambda:verifier)
        c=mysql_adapter.get_connection()
        try:
            with c.cursor() as cursor:
                for name in ['lu_nas_cancel_occupancy_v1']:
                    cursor.execute('SELECT ROUTINE_NAME FROM information_schema.routines WHERE routine_schema=DATABASE() AND routine_name=%s',(name,))
                    if not cursor.fetchone():
                        args,body,_=PROCEDURES[name]
                        cursor.execute(f'CREATE PROCEDURE {name} ({args}) SQL SECURITY INVOKER BEGIN {body} END')
            c.commit()
        finally:c.close()
        with TestClient(app,headers={'X-Correlation-ID':'service-start-test'}) as client:yield client


def write(sql,params=()):
    c=mysql_adapter.get_connection()
    try:
        with c.cursor() as cursor:
            cursor.execute(sql,params);identity=cursor.lastrowid
        c.commit();return identity
    finally:c.close()


def rows(sql,params=()):
    return h['rows'](sql,params)


def checked(response):
    assert response.status_code==200,response.text
    return response.json()['data']


def postponement_submission(http, case, staff, dates, *, assignment_id=None):
    from domains.scheduling.leave_result import LeaveDateChange, LeaveResultSubmission

    cases = checked(http.post(
        '/api/v1/line/staff-self-service/leave-results/cases', json={'line_id_token': staff[1]},
    ))['items']
    subject = next(item for item in cases if item['case_no'] == case
                   and (assignment_id is None or item['assignment_id'] == assignment_id))
    return LeaveResultSubmission(
        case, staff[0], subject['assignment_id'], 'defer',
        tuple(LeaveDateChange(date.fromisoformat(before), date.fromisoformat(after)) for before, after in dates),
        subject['order_version'], subject['scheduling_version'], uuid4().hex,
    )


def apply_confirmed_postponement(submission):
    """Enter the Scheduling owner at the point where the group handler has verified customer consent."""
    from api.dependencies.service_start import build_service_start_application
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork

    connection = mysql_adapter.get_connection()
    try:
        application = build_service_start_application(connection)
        with MySqlUnitOfWork(connection) as unit:
            result = application.submit_leave_in_current_unit_of_work(submission, enqueue_group_schedule=False)
            unit.commit()
        return asdict(result)
    finally:
        connection.close()


def seed_case(http,*,count=1, shared_staff=None, clock=("08:00:00", "17:00:00"), hours=8,
              with_commitment=True, with_contract_event=True):
    case='116'+str(rows('SELECT COUNT(*) n FROM orders')[0]['n']+1).zfill(6)
    client=write("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic service start','一般市民','連續服務','2026-10-01')",(case,))
    write("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,'2027-01-01',%s,%s,0,%s,%s,0)",(case,client,count*30,hours,*clock))
    base=f'/api/v1/orders/{case}/intake-completion'
    p=checked(http.post(base+'/preview',json={}))
    checked(http.post(base+'/apply',json={'expected_lifecycle_version':p['lifecycle_version'],'preview_fingerprint':p['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':case+':init'}))
    # Real Finance bank/receipt owner settles the prerequisite deposit.
    amount=rows("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='deposit'",(case,))[0]['amount_due_ntd']
    h['bank'](http,case,amount,1)
    staff=[]
    for index in range(count+2):
        if index == 0 and shared_staff is not None:
            staff.append(shared_staff)
            continue
        line='U'+uuid4().hex
        identity=write("INSERT INTO staff(name,status,line_user_id) VALUES (%s,'active',%s)",(f'Synthetic {case} {index}',line))
        write("INSERT INTO line_platform_users(line_user_id,friend_status) VALUES (%s,'active')",(line,))
        write("INSERT INTO line_identity_role_bindings(line_user_id,subject_type,binding_status,subject_reference) VALUES (%s,'staff','bound',%s)",(line,str(identity)))
        staff.append((identity,line))
    plan=write("INSERT INTO caregiver_matching_plans(case_no,status,is_active,start_date,end_date,created_by) VALUES (%s,'proposed',1,'2027-01-01',%s,'synthetic signed prerequisite')",(case,date(2027,1,1)+timedelta(days=count*30-1)))
    if with_commitment:
        commitment=write('INSERT INTO precontract_service_commitments(case_no,matching_plan_id,commitment_key,plan_snapshot_sha256,created_by) VALUES (%s,%s,%s,%s,%s)',(case,plan,case+':commitment','0'*64,'synthetic signed prerequisite'))
    segments=[]
    for index,(staff_id,line) in enumerate(staff[:count]):
        start=date(2027,1,1)+timedelta(days=index*30)
        segment=write('INSERT INTO caregiver_matching_plan_segments(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) VALUES (%s,%s,%s,%s,%s)',(plan,index+1,staff_id,start,start+timedelta(days=29)))
        segments.append(segment)
        if with_commitment:
            for i in range(30):write('INSERT INTO precontract_service_commitment_days(commitment_id,matching_segment_id,staff_id,service_date) VALUES (%s,%s,%s,%s)',(commitment,segment,staff_id,start+timedelta(days=i)))
    if with_contract_event:
        write("INSERT INTO order_contract_flow_events(case_no,contract_identity,event_type,actor,reason,idempotency_key) VALUES (%s,%s,'contract_completed','synthetic','signed fixture',%s)",(case,case+':signed',case+':signed'))
    # Signed client contract qualifies the canonical waiting-lock writer.
    write("INSERT INTO matching_response_events(plan_id,response_type,response_value,response_source,actor_id,reason,idempotency_key,payload_fingerprint,occurred_at_utc) VALUES (%s,'customer_decision','accepted','admin','synthetic','prerequisite',%s,%s,UTC_TIMESTAMP(6))",(plan,case+':customer','0'*64))
    write("INSERT INTO line_order_group_bindings(case_no,group_id,binding_status,aggregate_version,invitation_url) VALUES (%s,%s,'bound',1,%s)",(case,'C'+uuid4().hex,'https://line.me/R/ti/g/synthetic-'+case))
    write("INSERT INTO line_order_group_binding_events(case_no,action,expected_version,resulting_version,actor_id,binding_fingerprint,idempotency_key,correlation_id) VALUES (%s,'bound',0,1,'synthetic',%s,%s,%s)",(case,'0'*64,case+':group',case))
    return case,staff,segments


def submit(http,case,staff,segment,decision='accepted',start='2027-01-05',key=None):
    version=rows('SELECT lifecycle_version FROM orders WHERE case_no=%s',(case,))[0]['lifecycle_version']
    body={'line_id_token':staff[1],'case_no':case,'segment_id':segment,'decision':decision,
        'start_date':start if decision=='accepted' else None,'expected_order_version':version,'idempotency_key':key or uuid4().hex}
    return http.post('/api/v1/line/staff-self-service/service-start/submit',json=body),body


def test_normal_start_atomic_dates_finance_group_result_and_replay(http):
    case,staff,segments=seed_case(http)
    response,body=submit(http,case,staff[0],segments[0])
    result=checked(response)
    assert result['status']=='applied'
    assert result['result']['actual_start_date']=='2027-01-05'
    assert result['result']['first_payment_due_date']=='2027-01-05'
    assert len(result['result']['assignments'][0]['service_dates'])==30
    assert rows("SELECT COUNT(*) n FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(result['request_id']),))[0]['n']==1
    assert checked(http.post('/api/v1/line/staff-self-service/service-start/submit',json=body))['request_id']==result['request_id']
    assert rows("SELECT COUNT(*) n FROM scheduling_service_start_requests WHERE case_no=%s",(case,))[0]['n']==1
    assert checked(http.get('/api/v1/scheduling/service-start/todos',params={'case_no':case}))['total']==0


def test_formal_adjustment_preserves_valid_opening_reconfirmation(http):
    from domains.scheduling.service_date_adjustment import AdjustmentTarget
    from infrastructure.mysql.service_date_adjustment_repository import MySqlServiceDateAdjustmentRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.order_lifecycle_command_envelope import lock_order_lifecycle_command_envelope
    from subsystems.orders.order_lifecycle_control_commands import (
        ActualStartReconfirmationConfirmedCommand,
        ActualStartReconfirmationRequiredCommand,
        apply_order_lifecycle_control_command,
    )
    from subsystems.scheduling.service_date_adjustment import ServiceDateAdjustmentIntent, ServiceDateAdjustmentWorkflow

    case_no, staff, segments = seed_case(http, hours=4)
    response, _ = submit(http, case_no, staff[0], segments[0])
    assert checked(response)["status"] == "applied"
    connection = mysql_adapter.get_connection()
    try:
        workflow = ServiceDateAdjustmentWorkflow(
            MySqlServiceDateAdjustmentRepository(connection), lambda: MySqlUnitOfWork(connection),
        )
        facts = workflow.query(case_no)
        initial = facts.days[0].service_date
        next_start = facts.days[2].service_date
        assert facts.actual_start_date == initial
        with connection.cursor() as cursor:
            cursor.execute("SELECT settlement_identity FROM client_deposit_settlement_projection WHERE case_no=%s", (case_no,))
            settlement_identity = cursor.fetchone()["settlement_identity"]
            cursor.execute("SELECT id FROM scheduling_command_receipts WHERE case_no=%s ORDER BY id DESC LIMIT 1", (case_no,))
            assignment_receipt_id = cursor.fetchone()["id"]
            activate_key = f"test-reconfirmation-required:{case_no}"
            apply_order_lifecycle_control_command(
                cursor, lock_order_lifecycle_command_envelope(cursor, case_no, facts.order_version, activate_key),
                ActualStartReconfirmationRequiredCommand(
                    "admin", "test delayed settlement", facts.order_version, activate_key, initial, settlement_identity,
                ),
            )
            confirm_key = f"test-reconfirmation-cleared:{case_no}"
            confirmed = apply_order_lifecycle_control_command(
                cursor, lock_order_lifecycle_command_envelope(cursor, case_no, facts.order_version, confirm_key),
                ActualStartReconfirmationConfirmedCommand(
                    "admin", "test confirmed opening", facts.order_version, confirm_key, initial, initial,
                    settlement_identity, "a" * 64, {"scheduling_command_receipt_id": assignment_receipt_id},
                ),
            )
        connection.commit()

        intent = ServiceDateAdjustmentIntent(
            (initial, facts.days[1].service_date),
            (AdjustmentTarget(facts.days[-1].service_date + timedelta(days=1), staff[0][0]),),
        )
        preview = workflow.preview(case_no, intent)
        arguments = dict(versions=facts.versions, preview_fingerprint=preview.fingerprint, key="merge-after-opening", actor="admin")
        receipt = workflow.apply(case_no, intent, **arguments)
        assert workflow.apply(case_no, intent, **arguments) == receipt
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT entry.actual_start_date, control.state, control.confirmed_start_date, "
                "control.deposit_settlement_identity_hash, event.payload_snapshot "
                "FROM orders entry JOIN order_lifecycle_control_state control ON control.case_no=entry.case_no "
                "JOIN order_lifecycle_control_events event ON event.id=control.current_event_id "
                "WHERE entry.case_no=%s AND control.control_type='actual_start_reconfirmation'", (case_no,),
            )
            row = cursor.fetchone()
            snapshot = json.loads(row["payload_snapshot"])
            assert row["actual_start_date"] == row["confirmed_start_date"] == next_start
            assert row["state"] == "cleared"
            assert row["deposit_settlement_identity_hash"] == confirmed.projection.deposit_settlement_identity_hash
            assert snapshot["source_reconfirmation_event_id"] == confirmed.event_id
            assert snapshot["schedule_adjustment_receipt_id"] == receipt.receipt_id
            cursor.execute("SELECT payload_snapshot FROM order_lifecycle_control_events WHERE id=%s", (confirmed.event_id,))
            assert json.loads(cursor.fetchone()["payload_snapshot"])["new_actual_start_date"] == initial.isoformat()
    finally:
        connection.close()


@pytest.mark.parametrize(('placeholder', 'interleaved'), [(False, False), (True, False), (False, True)],
                         ids=['first-assignment', 'empty-assignment', 'interleaved'])
def test_office_schedule_saves_dates_and_caregivers_once(http, placeholder, interleaved):
    from api.routes.service_date_confirmation import router

    if not getattr(http.app.state, 'service_dates_registered', False):
        http.app.include_router(router)
        http.app.state.service_dates_registered = True
    count = 1 if placeholder else 2
    case, staff, _ = seed_case(http, count=count)
    # The signing prerequisite above seeds its event. Mirror the completed signing projection.
    write("UPDATE orders SET status='訂單成立' WHERE case_no=%s", (case,))
    if placeholder:
        generation = write("INSERT INTO scheduling_generations (case_no,generation_number,resulting_aggregate_version,"
                           "status,effective_marker,created_by,change_reason) VALUES (%s,1,1,'effective',1,'fixture','fixture')",
                           (case,))
        previous_assignment = write("INSERT INTO case_staff_assignments (case_no,generation_id,candidate_key,staff_id,"
                                    "assignment_sequence,assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
                                    "VALUES (%s,%s,%s,%s,1,'2027-01-01','2027-01-30',0,'active')",
                                    (case,generation,case+':placeholder',staff[0][0]))
        write("INSERT INTO assignment_payroll_rate_snapshots (assignment_id,policy_version,policy_kind,hourly_rate_ntd,"
              "source_identity_status) SELECT %s,policy_version,policy_kind,hourly_rate_ntd,source_identity_status "
              "FROM case_payroll_rate_policy_snapshots WHERE case_no=%s", (previous_assignment,case))
        write("INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter,effective_generation_id) "
              "VALUES (%s,1,1,%s) ON DUPLICATE KEY UPDATE aggregate_version=1,generation_counter=1,effective_generation_id=%s",
              (case,generation,generation))
    endpoint = f'/api/v1/orders/{case}/service-dates'
    before = checked(http.get(endpoint))
    days = tuple(date(2027, 1, 5) + timedelta(days=i) for i in range(count*30))
    allocations = [days[i::count] if interleaved else days[i*30:(i+1)*30] for i in range(count)]
    if interleaved:
        allocations[1] = allocations[1] + allocations[0][-1:]
        allocations[0] = allocations[0][:-1]
        allocations[1] = tuple(sorted(allocations[1]))
    body = {
        'actual_start_date': '2027-01-04', 'expected_order_version': before['order_version'],
        'expected_scheduling_version': before['scheduling_version'],
        'expected_confirmed_version': before['current_version'], 'reason': '',
        'segments': [{'staff_id': staff[i][0], 'service_dates': list(map(str, dates))}
                     for i, dates in enumerate(allocations)],
    }
    headers = {'Idempotency-Key': case + ':office'}
    if interleaved:
        blocked = http.post(endpoint + '/office-schedule/apply', json=body, headers=headers)
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()['detail']['error']['code'] == 'office_schedule_reallocation_reason_required'
        assert checked(http.get(endpoint)) == before
        body['reason'] = '確認兩位月嫂交錯服務與天數調整'
    saved = checked(http.post(endpoint + '/office-schedule/apply', json=body, headers=headers))
    assert checked(http.post(endpoint + '/office-schedule/apply', json=body, headers=headers)) == saved
    observed = checked(http.get(endpoint))
    assert observed['current_dates'] == list(map(str, days))
    assert observed['scheduling_version'] == saved['scheduling_version']
    assert rows('SELECT actual_start_date FROM orders WHERE case_no=%s', (case,))[0]['actual_start_date'] == date(2027, 1, 5)
    work_days = rows("SELECT staff_id,work_date FROM staff_schedule WHERE case_no=%s "
                     "AND effective_marker=1 AND is_work_day=1 ORDER BY work_date", (case,))
    expected_by_day = {day: staff[index][0] for index, allocation in enumerate(allocations) for day in allocation}
    assert [(row['staff_id'], row['work_date']) for row in work_days] == [(expected_by_day[day], day) for day in days]
    assert len(saved['assignment_ids']) == count
    if placeholder:
        assert rows('SELECT status FROM case_staff_assignments WHERE id=%s', (previous_assignment,))[0]['status'] == 'cancelled'
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no':case}))['total'] == 0


@pytest.mark.parametrize(('missing', 'error_code'), [
    ('active_plan', 'office_schedule_commitment_blocked'),
    ('commitment', 'office_schedule_signed_archive_blocked'),
    ('availability', 'staff_occupancy_conflict'),
])
def test_office_schedule_direct_save_blocks_missing_prerequisites(http, missing, error_code):
    from api.routes.service_date_confirmation import router

    if not getattr(http.app.state, 'service_dates_registered', False):
        http.app.include_router(router)
        http.app.state.service_dates_registered = True
    case, staff, _ = seed_case(http, with_commitment=missing != 'commitment')
    write("UPDATE orders SET status='訂單成立' WHERE case_no=%s", (case,))
    if missing == 'active_plan':
        write("UPDATE caregiver_matching_plans SET is_active=NULL WHERE case_no=%s", (case,))
    if missing == 'availability':
        write(
            "INSERT INTO scheduling_staff_unavailability_blocks "
            "(staff_id,block_kind,start_date,end_date,status,reason,created_by) "
            "VALUES (%s,'long_leave','2027-01-05','2027-01-05','effective','fixture','fixture')",
            (staff[0][0],),
        )
    endpoint = f'/api/v1/orders/{case}/service-dates'
    before = checked(http.get(endpoint))
    days = [str(date(2027, 1, 5) + timedelta(days=index)) for index in range(30)]
    response = http.post(endpoint + '/office-schedule/apply', json={
        'actual_start_date': days[0], 'expected_order_version': before['order_version'],
        'expected_scheduling_version': before['scheduling_version'],
        'expected_confirmed_version': before['current_version'], 'reason': '',
        'segments': [{'staff_id': staff[0][0], 'service_dates': days}],
    }, headers={'Idempotency-Key': case + ':office'})
    assert response.status_code == 409, response.text
    assert response.json()['detail']['error']['code'] == error_code
    assert checked(http.get(endpoint)) == before
    assert not rows('SELECT id FROM staff_schedule WHERE case_no=%s', (case,))


@pytest.mark.parametrize("fail_after_commitment", [False, True], ids=["save-and-replay", "rollback"])
def test_office_first_schedule_creates_commitment_after_real_archive(
    http, monkeypatch, tmp_path, fail_after_commitment,
):
    from api.dependencies import contract_external_signing as dependencies
    from api.routes import contract_external_signing, service_date_confirmation
    from infrastructure.mysql import service_start_arrangement

    if not getattr(http.app.state, 'service_dates_registered', False):
        http.app.include_router(service_date_confirmation.router)
        http.app.state.service_dates_registered = True
    if not getattr(http.app.state, 'archive_registered', False):
        http.app.include_router(contract_external_signing.router)
        http.app.state.archive_registered = True
    monkeypatch.setattr(dependencies, '_controlled_file_storage_root', lambda: tmp_path)
    monkeypatch.setattr(dependencies, '_contract_archive_root', lambda: tmp_path)
    case, staff, segments = seed_case(http, with_commitment=False, with_contract_event=False)
    endpoint = f'/api/v1/orders/{case}/service-dates'
    original_dates = [str(date(2027, 1, 1) + timedelta(days=i)) for i in range(30)]
    preview = checked(http.post(endpoint + '/preview', json={'service_dates': original_dates}))
    checked(http.post(endpoint + '/apply', json={
        'service_dates': original_dates, 'expected_order_version': preview['order_version'],
        'expected_scheduling_version': preview['scheduling_version'],
        'preview_fingerprint': preview['preview_fingerprint'], 'reason': 'synthetic original agreement',
    }, headers={'Idempotency-Key': case + ':original-dates'}))
    pdf = b'%PDF-1.4\nTEST ONLY - NOT A SIGNED CONTRACT\n%%EOF\n'
    archive = checked(http.post(f'/api/v1/orders/{case}/contract-external-signing/signed-archive',
        files=[('client', ('client-test.pdf', pdf, 'application/pdf')),
               ('staff', ('staff-test.pdf', pdf, 'application/pdf'))],
        data={'staff_segment_ids': [str(segments[0])]},
        headers={'Idempotency-Key': case + ':archive'}))
    assert len(archive['files']) == 2
    assert rows('SELECT status FROM orders WHERE case_no=%s', (case,))[0]['status'] == '訂單成立'
    assert not rows('SELECT id FROM precontract_service_commitments WHERE case_no=%s', (case,))
    finance_before = rows('SELECT obligation_identity,obligation_type,amount_due_ntd FROM client_obligations '
                          'WHERE case_no=%s ORDER BY obligation_identity', (case,))
    before = checked(http.get(endpoint))
    dates = [str(date(2027, 1, 5) + timedelta(days=i)) for i in range(30)]
    allocation = [{'staff_id': staff[0][0], 'service_dates': dates}]
    draft = checked(http.post(endpoint + '/office-schedule/preview', json={
        'actual_start_date': dates[0], 'segments': allocation, 'reason': '',
        'expected_order_version': before['order_version'],
        'expected_scheduling_version': before['scheduling_version'],
        'expected_confirmed_version': before['current_version'],
    }))
    assert len(draft['preview_fingerprint']) == 64
    assert not rows('SELECT id FROM precontract_service_commitments WHERE case_no=%s', (case,))
    if fail_after_commitment:
        from infrastructure.db.external_staff_completion_port import MySqlExternalStaffCompletionPort
        established = []
        original_ensure = MySqlExternalStaffCompletionPort.ensure_archived_commitment
        def observe_establishment(port, command):
            identity = original_ensure(port, command)
            with port._connection.cursor() as cursor:
                cursor.execute('SELECT id FROM precontract_service_commitments WHERE case_no=%s', (case,))
                assert cursor.fetchone()['id'] == identity
            established.append(identity)
            return identity
        monkeypatch.setattr(MySqlExternalStaffCompletionPort, 'ensure_archived_commitment', observe_establishment)
        def reject_after_write(*args):
            assert len(established) == 1
            raise ValueError('office_schedule_forced_conflict')
        monkeypatch.setattr(service_start_arrangement, '_office_assignment_intent', reject_after_write)
    body = {
        'actual_start_date': dates[0], 'expected_order_version': before['order_version'],
        'expected_scheduling_version': before['scheduling_version'],
        'expected_confirmed_version': before['current_version'], 'reason': '', 'segments': allocation,
    }
    response = http.post(endpoint + '/office-schedule/apply', json=body,
                         headers={'Idempotency-Key': case + ':archive-office'})
    if fail_after_commitment:
        assert response.status_code == 409, response.text
        assert response.json()['detail']['error']['code'] == 'office_schedule_forced_conflict'
        assert not rows('SELECT id FROM precontract_service_commitments WHERE case_no=%s', (case,))
        assert checked(http.get(endpoint)) == before
        assert not rows('SELECT id FROM staff_schedule WHERE case_no=%s', (case,))
    else:
        saved = checked(response)
        replay = checked(http.post(endpoint + '/office-schedule/apply', json=body,
                                   headers={'Idempotency-Key': case + ':archive-office'}))
        assert replay == saved
        commitments = rows('SELECT id FROM precontract_service_commitments WHERE case_no=%s', (case,))
        assert len(commitments) == 1
        signed = rows('SELECT staff_id,service_date FROM precontract_service_commitment_days '
                      'WHERE commitment_id=%s ORDER BY service_date', (commitments[0]['id'],))
        assert [(item['staff_id'], str(item['service_date'])) for item in signed] == [
            (staff[0][0], day) for day in original_dates
        ]
        scheduled = rows('SELECT staff_id,work_date FROM staff_schedule WHERE case_no=%s '
                         'AND effective_marker=1 AND is_work_day=1 ORDER BY work_date', (case,))
        assert [(item['staff_id'], str(item['work_date'])) for item in scheduled] == [
            (staff[0][0], day) for day in dates
        ]
        assert checked(http.get(endpoint))['current_dates'] == dates
    assert rows('SELECT obligation_identity,obligation_type,amount_due_ntd FROM client_obligations '
                'WHERE case_no=%s ORDER BY obligation_identity', (case,)) == finance_before
    assert not rows("SELECT id FROM contract_signing_events WHERE case_no=%s AND event_type='signed_received'", (case,))


def test_office_schedule_preview_detects_assignment_linked_to_another_case(http):
    from api.routes.service_date_confirmation import router

    if not getattr(http.app.state, 'service_dates_registered', False):
        http.app.include_router(router)
        http.app.state.service_dates_registered = True
    case, staff, _ = seed_case(http)
    other_case, _, _ = seed_case(http)
    generation = write(
        "INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,"
        "status,effective_marker,created_by,change_reason) VALUES(%s,1,1,'effective',1,'fixture','fixture')",
        (other_case,),
    )
    assignment = write(
        "INSERT INTO case_staff_assignments(case_no,generation_id,staff_id,assignment_sequence,status) "
        "VALUES(%s,%s,%s,1,'active')", (case, generation, staff[0][0]),
    )
    write("UPDATE orders SET status='訂單成立' WHERE case_no=%s", (case,))
    endpoint = f'/api/v1/orders/{case}/service-dates'
    before = checked(http.get(endpoint))
    days = [str(date(2027, 1, 5) + timedelta(days=index)) for index in range(30)]
    body = {
        'actual_start_date': days[0], 'expected_order_version': before['order_version'],
        'expected_scheduling_version': before['scheduling_version'],
        'expected_confirmed_version': before['current_version'], 'reason': '',
        'segments': [{'staff_id': staff[0][0], 'service_dates': days}],
    }
    for action in ('preview', 'apply'):
        response = http.post(f'{endpoint}/office-schedule/{action}', json=body,
                             headers={'Idempotency-Key': case + ':office'})
        assert response.status_code == 409, response.text
        assert response.json()['detail']['error']['code'] == 'office_schedule_assignment_ownership_blocked'
    assert checked(http.get(endpoint)) == before
    assert rows('SELECT generation_id FROM case_staff_assignments WHERE id=%s', (assignment,))[0]['generation_id'] == generation
    assert rows('SELECT COUNT(*) total FROM staff_schedule WHERE case_no=%s', (case,))[0]['total'] == 0


def test_same_staff_same_day_nonoverlapping_shifts_commit_and_read_back(http):
    morning, staff, morning_segments = seed_case(http, clock=("08:00", "12:00"), hours=4)
    afternoon, _, afternoon_segments = seed_case(http, shared_staff=staff[0], clock=("13:00", "17:00"), hours=4)
    responses = _concurrent_starts(http, staff[0], ((morning, morning_segments[0]), (afternoon, afternoon_segments[0])))
    assert [checked(response)["status"] for response in responses] == ["applied", "applied"]
    calendar = checked(http.post(
        "/api/v1/line/staff-self-service/schedule",
        params={"year": 2027, "month": 1}, json={"line_id_token": staff[0][1]},
    ))
    shifts = [entry for entry in calendar["days"] if entry["work_date"] == "2027-01-05" and entry["status"] == "working"]
    assert [(entry["case_no"], entry["starts_at"][11:16], entry["ends_at"][11:16]) for entry in shifts] == [
        (morning, "08:00", "12:00"), (afternoon, "13:00", "17:00"),
    ]
    result = apply_confirmed_postponement(postponement_submission(
        http, afternoon, staff[0], [('2027-01-05', '2027-02-10')],
    ))
    assert result["status"] == "applied"
    after = rows(
        "SELECT case_no FROM staff_schedule WHERE staff_id=%s AND work_date='2027-01-05' "
        "AND effective_marker=1 AND is_work_day=1",
        (staff[0][0],),
    )
    assert [entry["case_no"] for entry in after] == [morning]


def test_concurrent_overlapping_service_starts_leave_one_effective_shift(http):
    first, staff, first_segments = seed_case(http, clock=("08:00", "12:00"), hours=4)
    second, _, second_segments = seed_case(http, shared_staff=staff[0], clock=("11:30", "15:30"), hours=4)
    responses = _concurrent_starts(http, staff[0], ((first, first_segments[0]), (second, second_segments[0])))
    assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
    assert next(response for response in responses if response.status_code == 200).json()["data"]["status"] == "applied"
    assert len(rows('SELECT id FROM scheduling_service_start_requests WHERE case_no IN (%s,%s)', (first, second))) == 1
    effective = rows(
        "SELECT case_no FROM staff_schedule WHERE staff_id=%s AND work_date='2027-01-05' "
        "AND effective_marker=1 AND is_work_day=1 AND case_no IN (%s,%s)",
        (staff[0][0], first, second),
    )
    assert len(effective) == 1


def _concurrent_starts(http, staff, pairs):
    barrier = Barrier(2)

    def attempt(value):
        case, segment = value
        barrier.wait(timeout=10)
        return submit(http, case, staff, segment)[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        return tuple(executor.map(attempt, pairs))


def test_historical_refusal_replays_and_new_refusal_returns_gone(http):
    from domains.scheduling.service_start import ServiceStartDecision, ServiceStartSubmission
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository

    case, staff, segments = seed_case(http)
    request = seed_legacy_pending(case, staff[0][0])
    old = checked(http.get(f'/api/v1/scheduling/service-start/{request}'))
    key = uuid4().hex
    submission = ServiceStartSubmission(case, staff[0][0], segments[0], ServiceStartDecision.DECLINED,
                                        None, old['order_version'], key)
    write('UPDATE scheduling_service_start_requests SET segment_id=%s,submit_key=%s,submit_fingerprint=%s WHERE id=%s',
          (segments[0], key, MySqlServiceStartRepository._submission_fingerprint(submission), request))
    before = owner_state(case)
    deliveries = rows('SELECT COUNT(*) AS total FROM line_delivery_tasks')
    response, body = submit(http, case, staff[0], segments[0], decision='declined', key=key)
    result = checked(response)
    assert result['status'] == 'substitute_required'
    assert result == checked(http.get(f'/api/v1/scheduling/service-start/{request}'))
    path = '/api/v1/line/staff-self-service/service-start/submit'
    for changes in ({'expected_order_version': body['expected_order_version'] + 1},
                    {'line_id_token': staff[1][1]}, {'case_no': case + '-different'}):
        changed = http.post(path, json={**body, **changes})
        assert changed.status_code == 409
        assert changed.json()['detail']['error']['code'] == 'service_start_key_reused'
    response = http.post(path, json={**body, 'idempotency_key': uuid4().hex})
    assert response.status_code == 410
    assert response.json()['detail']['error']['code'] == 'service_start_coordination_retired'
    assert owner_state(case) == before
    assert rows('SELECT COUNT(*) AS total FROM line_delivery_tasks') == deliveries
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no': case}))['total'] == 0

def action(http,item,kind,**fields):
    body={'expected_version':item['version'],'idempotency_key':uuid4().hex,**fields}
    return checked(http.post(f"/api/v1/scheduling/service-start/{item['request_id']}/{kind}",json=body)),body


def willingness(item,staff,decision):
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from subsystems.line.matching_postback_application import LineMatchingPostbackApplication
    from domains.line.identities import LineSourceType,LineUserId
    task=rows("SELECT payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_type='service_start_inquiry' AND source_aggregate_identity=(SELECT selected_candidate_id FROM scheduling_service_start_requests WHERE id=%s) ORDER BY id DESC LIMIT 1",(item['request_id'],))[0]
    payload=json.loads(task['payload_snapshot'])
    data=next(button['action']['data'] for button in payload['contents']['footer']['contents'] if button['action']['data'].endswith(':'+decision))
    event=SimpleNamespace(source=SimpleNamespace(source_type=LineSourceType.USER,user_id=LineUserId(staff[1])),payload_json=json.dumps({'postback':{'data':data}}),event_id=SimpleNamespace(value=uuid4().hex))
    c=mysql_adapter.get_connection()
    try:
        with LineMySqlUnitOfWork(c) as unit:
            LineMatchingPostbackApplication(None).handle(SimpleNamespace(event=event),unit)
            unit.commit()
    finally:c.close()


def joined(case,staff,event_type='member_joined'):
    from infrastructure.mysql.line_media_order_group_repository import MySqlLineOrderGroupBindingRepository
    from domains.line.identities import LineUserId
    from shared_kernel.identities import IdempotencyKey
    c=mysql_adapter.get_connection()
    try:
        group=rows('SELECT group_id FROM line_order_group_bindings WHERE case_no=%s',(case,))[0]['group_id']
        MySqlLineOrderGroupBindingRepository(c).record_membership_event(group_id=group,line_user_id=LineUserId(staff[1]),event_type=event_type,idempotency_key=IdempotencyKey(uuid4().hex),occurred_at=datetime.now(timezone.utc))
        c.commit()
    finally:c.close()


def test_retired_candidate_willingness_does_not_write(http):
    from hashlib import sha256
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository

    case, staff, _ = seed_case(http)
    item = seed_legacy_pending(case, staff[0][0])
    token = uuid4().hex
    candidate_id = write(
        "INSERT INTO scheduling_service_start_candidates "
        "(request_id,staff_id,proposed_start_date,proposed_end_date,interaction_hash) "
        "VALUES (%s,%s,'2027-01-05','2027-02-03',%s)",
        (item, staff[1][0], sha256(token.encode()).hexdigest()),
    )
    write('UPDATE scheduling_service_start_requests SET selected_candidate_id=%s WHERE id=%s', (candidate_id, item))
    connection = mysql_adapter.get_connection()
    try:
        assert not MySqlServiceStartRepository(connection).record_willingness(token, staff[1][1], 'willing', uuid4().hex)
        connection.commit()
    finally:
        connection.close()
    assert rows('SELECT willingness FROM scheduling_service_start_candidates WHERE id=%s', (candidate_id,)) == [{'willingness': 'pending'}]

def test_multiple_caregivers_wait_for_all_results_then_apply_once(http):
    case,staff,segments=seed_case(http,count=2)
    first=checked(submit(http,case,staff[0],segments[0])[0])
    assert first['status']=='awaiting_peers'
    assert rows('SELECT actual_start_date FROM orders WHERE case_no=%s',(case,))[0]['actual_start_date'] is None
    last=checked(submit(http,case,staff[1],segments[1],start='2027-02-04')[0])
    assert last['status']=='applied'
    assert len(last['result']['assignments'])==2
    assert checked(http.get(f"/api/v1/scheduling/service-start/{first['request_id']}"))['status']=='applied'
    assert len(rows("SELECT * FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(last['request_id']),)))==1


def owner_state(case):
    return {
        table: rows(f'SELECT * FROM {table} WHERE case_no=%s ORDER BY {key}', (case,))
        for table, key in (
            ('orders', 'case_no'), ('confirmed_service_date_versions', 'id'),
            ('scheduling_service_start_requests', 'id'), ('scheduling_generations', 'id'),
            ('case_staff_assignments', 'id'), ('staff_schedule', 'id'),
            ('client_payment_terms', 'case_no'), ('client_obligations', 'obligation_identity'),
            ('client_ledger_entries', 'id'), ('staff_obligations', 'obligation_identity'),
        )
    }


def seed_legacy_pending(case, staff_id, *, assignment_id=None, execution=None):
    return write(
        "INSERT INTO scheduling_service_start_requests "
        "(case_no,staff_id,assignment_id,decision,source_order_version,status,submit_key,submit_fingerprint,execution_dates) "
        "SELECT case_no,%s,%s,'declined',lifecycle_version,'substitute_required',%s,%s,%s "
        "FROM orders WHERE case_no=%s",
        (staff_id, assignment_id, uuid4().hex, '0' * 64, json.dumps(execution) if execution else None, case),
    )


def test_occupancy_conflict_keeps_official_dates_unchanged_and_rejects_new_todo(http):
    case, staff, segments = seed_case(http)
    write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) "
          "VALUES (%s,'long_leave','2027-01-05','2027-02-10','effective','synthetic private time','synthetic')", (staff[0][0],))
    before = owner_state(case)
    response, _ = submit(http, case, staff[0], segments[0])
    assert response.status_code == 409
    assert response.json()['detail']['error']['code'] == 'staff_unavailable'
    assert owner_state(case) == before
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no': case}))['total'] == 0


@pytest.mark.parametrize('postpone', [False, True], ids=['open', 'defer'])
@pytest.mark.parametrize('historical', [False, True], ids=['new-conflict', 'saved-conflict'])
def test_group_conflict_commits_only_reply_and_never_creates_request(http, postpone, historical):
    from api.dependencies.service_start import build_service_start_application
    from domains.scheduling.service_start import ServiceStartConflict, ServiceStartDecision, ServiceStartSubmission
    from infrastructure.mysql.leave_result_repository import submission_fingerprint
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
    from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
    from subsystems.line.group_helper_application import (
        LineGroupHelperApplication, _FAMILY_POSTPONE_PROPOSAL, _FAMILY_START_PROPOSAL, save_group_helper_proposal,
    )

    case, staff, segments = seed_case(http)
    if postpone:
        checked(submit(http, case, staff[0], segments[0])[0])
        submission = postponement_submission(http, case, staff[0], [('2027-01-05', '2027-02-10')])
        first_day = '2027-02-10'
        preview = checked(http.post('/api/v1/line/staff-self-service/leave-results/preview', json={
            'line_id_token': staff[0][1], 'case_no': case, 'assignment_id': submission.assignment_id,
            'dates': [{'original_date': '2027-01-05', 'new_date': first_day}],
        }))
        assert not preview['conflict']
    else:
        first_day = '2027-01-05'
    group = rows('SELECT group_id FROM line_order_group_bindings WHERE case_no=%s', (case,))[0]['group_id']
    event_id = uuid4().hex
    order_version = rows('SELECT lifecycle_version FROM orders WHERE case_no=%s', (case,))[0]['lifecycle_version']
    if historical:
        if postpone:
            submission = replace(submission, key=f'group-helper-postpone:{case}:{event_id}')
            execution = {'kind': 'leave-v1', 'decision': 'defer',
                         'dates': [{'original_date': '2027-01-05', 'new_date': first_day}]}
            request = seed_legacy_pending(case, staff[0][0], assignment_id=submission.assignment_id,
                                          execution=execution)
            fingerprint = submission_fingerprint(submission)
            segment_id = None
        else:
            submission = ServiceStartSubmission(case, staff[0][0], segments[0], ServiceStartDecision.ACCEPTED,
                                                date.fromisoformat(first_day), order_version,
                                                f'group-helper-start:{case}:{event_id}')
            request = seed_legacy_pending(case, staff[0][0])
            fingerprint = MySqlServiceStartRepository._submission_fingerprint(submission)
            segment_id = segments[0]
        write("UPDATE scheduling_service_start_requests SET decision='accepted',requested_start_date=%s,"
              'segment_id=%s,submit_key=%s,submit_fingerprint=%s WHERE id=%s',
              (first_day, segment_id, submission.key, fingerprint, request))
    else:
        write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) "
              "VALUES (%s,'long_leave',%s,%s,'effective','synthetic','synthetic')", (staff[0][0], first_day, first_day))
    before = owner_state(case)
    if historical and postpone:
        deliveries_before = rows('SELECT COUNT(*) AS total FROM line_delivery_tasks')
        replay = apply_confirmed_postponement(submission)
        assert (replay['request_id'], replay['status']) == (request, 'substitute_required')
        with pytest.raises(ServiceStartConflict) as changed:
            apply_confirmed_postponement(replace(submission, expected_scheduling_version=submission.expected_scheduling_version + 1))
        assert changed.value.code == 'leave_result_key_reused'
        with pytest.raises(ServiceStartConflict) as retired:
            apply_confirmed_postponement(replace(
                submission, decision='substitute', key=uuid4().hex,
                dates=tuple(replace(day, new_date=None) for day in submission.dates),
            ))
        assert retired.value.code == 'service_start_coordination_retired'
        assert rows('SELECT COUNT(*) AS total FROM line_delivery_tasks') == deliveries_before
    inbox = SimpleNamespace(event=SimpleNamespace(
        event_id=SimpleNamespace(value=event_id), occurred_at=datetime.now(timezone.utc),
        source=SimpleNamespace(user_id=SimpleNamespace(value='U-synthetic-customer')),
    ))
    ctx = {'case_no': case, 'staff_id': staff[0][0], 'segment_id': segments[0],
           'order_version': order_version,
           'is_staff': False, 'is_customer': True, 'is_admin': False}
    connection = mysql_adapter.get_connection()
    try:
        application = LineGroupHelperApplication(service_start_factory=build_service_start_application)
        with LineMySqlUnitOfWork(connection) as unit:
            if postpone:
                ref = uuid4().hex
                ctx['scheduling_version'] = submission.expected_scheduling_version
                save_group_helper_proposal(unit, _FAMILY_POSTPONE_PROPOSAL, case, ref, {
                    'proposal_ref': ref, 'staff_id': staff[0][0], 'assignment_id': submission.assignment_id,
                    'dates': [{'original_date': '2027-01-05', 'new_date': first_day}],
                    'leave_start_date': '2027-01-05', 'leave_end_date': '2027-01-05',
                })
                application._handle_postponement_agree(inbox, unit, group, ctx, ref)
            else:
                save_group_helper_proposal(unit, _FAMILY_START_PROPOSAL, case, uuid4().hex, {'start_date': first_day})
                application._handle_confirm_start_agree(inbox, unit, group, ctx)
            unit.commit()
    finally:
        connection.close()

    assert owner_state(case) == before
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no': case}))['total'] == 0
    deliveries = rows("SELECT source_aggregate_type,payload_snapshot FROM line_delivery_tasks "
                      "WHERE correlation_id=%s ORDER BY id", ('line-event:' + event_id,))
    assert [row['source_aggregate_type'] for row in deliveries] == [REPLY_ONLY_WEBHOOK_SOURCE]
    message = json.loads(deliveries[0]['payload_snapshot'])['text']
    assert ('延期補班未完成' if postpone else '開工確認未完成') in message
    assert ('請從原案件的多月嫂排班調整。' if historical else '不可排班') in message
    receipts = rows('SELECT result_reference FROM line_command_receipts WHERE command_family=%s AND correlation_id=%s',
                    (_FAMILY_POSTPONE_PROPOSAL if postpone else _FAMILY_START_PROPOSAL, f'case:{case}'))
    assert len(receipts) == 1 and receipts[0]['result_reference'] != 'cleared'

def test_staff_object_scope_validation_and_stale_rollback(http):
    case,staff,segments=seed_case(http)
    response,body=submit(http,case,staff[1],segments[0])
    assert response.status_code==409
    response,body=submit(http,case,staff[0],segments[0],start=None)
    assert response.status_code==409
    body['start_date']='2027-01-05';body['expected_order_version']-=1
    assert http.post('/api/v1/line/staff-self-service/service-start/submit',json=body).status_code==409
    assert not rows('SELECT * FROM scheduling_service_start_requests WHERE case_no=%s',(case,))


def test_staff_cases_keep_distinct_formal_assignment_identity(http):
    case, staff, segments = seed_case(http)
    checked(submit(http, case, staff[0], segments[0], start='2026-10-05')[0])
    own = checked(http.post('/api/v1/line/staff-self-service/service-start/cases', json={'line_id_token': staff[0][1]}))['items']
    own = [item for item in own if item['case_no'] == case]
    current = rows('SELECT a.id FROM case_staff_assignments a JOIN scheduling_aggregates g '
                   'ON g.effective_generation_id=a.generation_id WHERE a.case_no=%s AND a.staff_id=%s', (case, staff[0][0]))
    assert len(own) == len(current) == 1
    assert {item['assignment_id'] for item in own} == {item['id'] for item in current}
    assert all(item['segment_start_date'] and item['segment_end_date'] for item in own)

def test_future_start_day_advances_only_orders_without_rescheduling_or_extra_message(http):
    from infrastructure.mysql.service_start_lifecycle_repository import MySqlServiceStartLifecycleRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.service_start_lifecycle import ServiceStartLifecycleWorkflow
    from shared_kernel.clock import TAIPEI_TIME_ZONE
    case,staff,segments=seed_case(http)
    checked(submit(http,case,staff[0],segments[0])[0])
    assert rows('SELECT status FROM orders WHERE case_no=%s',(case,))[0]['status']=='訂單成立'
    before=rows('SELECT * FROM staff_schedule WHERE case_no=%s ORDER BY id',(case,))
    messages=rows('SELECT COUNT(*) n FROM line_delivery_tasks')[0]['n']
    c=mysql_adapter.get_connection()
    try:
        flow=ServiceStartLifecycleWorkflow(MySqlServiceStartLifecycleRepository(c),lambda:MySqlUnitOfWork(c))
        assert flow.advance_due(datetime(2027,1,4,tzinfo=TAIPEI_TIME_ZONE))==0
        assert flow.advance_due(datetime(2027,1,5,tzinfo=TAIPEI_TIME_ZONE))>=1
        assert not MySqlServiceStartLifecycleRepository(c).advance(case,datetime(2027,1,6,tzinfo=TAIPEI_TIME_ZONE))
        c.rollback()
    finally:c.close()
    assert rows('SELECT status FROM orders WHERE case_no=%s',(case,))[0]['status']=='服務中'
    assert rows('SELECT * FROM staff_schedule WHERE case_no=%s ORDER BY id',(case,))==before
    assert rows('SELECT COUNT(*) n FROM line_delivery_tasks')[0]['n']==messages


def test_concurrent_same_command_has_one_generation_and_one_group_result(http):
    from concurrent.futures import ThreadPoolExecutor
    case,staff,segments=seed_case(http)
    version=rows('SELECT lifecycle_version FROM orders WHERE case_no=%s',(case,))[0]['lifecycle_version']
    body={'line_id_token':staff[0][1],'case_no':case,'segment_id':segments[0],'decision':'accepted','start_date':'2027-01-05','expected_order_version':version,'idempotency_key':uuid4().hex}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:http.post('/api/v1/line/staff-self-service/service-start/submit',json=body),range(2)))
    values=[checked(r) for r in responses]
    assert values[0]['request_id']==values[1]['request_id']
    assert len(rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,)))==1
    assert len(rows("SELECT * FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(values[0]['request_id']),)))==1


def test_infrastructure_failure_rolls_back_all_dates_finance_and_outbox(http,monkeypatch):
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
    case,staff,segments=seed_case(http)
    before=rows('SELECT * FROM orders WHERE case_no=%s',(case,))
    finance=rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))
    def fail(*_, **_kwargs):raise RuntimeError('synthetic failure before commit')
    monkeypatch.setattr(MySqlServiceStartRepository,'complete',fail)
    with pytest.raises(RuntimeError,match='synthetic failure before commit'):
        submit(http,case,staff[0],segments[0])
    assert rows('SELECT * FROM orders WHERE case_no=%s',(case,))==before
    assert rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))==finance
    assert not rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,))
    assert not rows('SELECT * FROM scheduling_service_start_requests WHERE case_no=%s',(case,))


def test_retired_invitation_remains_redacted_and_is_cancelled_before_delivery(http):
    from domains.line.canonical_payload import canonical_line_payload_json
    from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
    from domains.line.identities import LineUserId
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from shared_kernel.identities import CorrelationId, IdempotencyKey
    from subsystems.line.delivery_worker import service_start_delivery_is_current

    case, staff, _ = seed_case(http)
    request = seed_legacy_pending(case, staff[0][0])
    candidate_id = write(
        "INSERT INTO scheduling_service_start_candidates "
        "(request_id,staff_id,proposed_start_date,proposed_end_date,willingness,interaction_hash) "
        "VALUES (%s,%s,'2027-01-05','2027-02-03','willing',%s)",
        (request, staff[1][0], '0' * 32 + uuid4().hex),
    )
    identity = f'{candidate_id}:legacy'
    write('UPDATE scheduling_service_start_requests SET selected_candidate_id=%s WHERE id=%s', (candidate_id, request))
    write('UPDATE scheduling_service_start_candidates SET invitation_identity=%s WHERE id=%s', (identity, candidate_id))
    payload = canonical_line_payload_json({'type': 'flex', 'altText': 'Invitation', 'contents': {'type': 'bubble', 'footer': {
        'type': 'box', 'layout': 'vertical', 'contents': [{'type': 'button', 'action': {
            'type': 'uri', 'label': 'Invitation', 'uri': 'https://line.me/R/ti/g/synthetic',
        }}],
    }}})
    connection = mysql_adapter.get_connection()
    try:
        with LineMySqlUnitOfWork(connection) as unit:
            task = unit.delivery_tasks.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, LineUserId(staff[1][1])),
                LineMessageKind.FLEX, payload, datetime.now(timezone.utc),
                IdempotencyKey(uuid4().hex), CorrelationId(case), 'service_start_invitation', identity,
            ))
            unit.commit()
        with LineMySqlUnitOfWork(connection) as unit:
            assert 'https://line.me/' not in str(unit.delivery_tasks.get_admin(task.task_id))
            assert not service_start_delivery_is_current(unit, unit.delivery_tasks.get(task.task_id))
        assert rows('SELECT processing_status FROM line_delivery_tasks WHERE id=%s', (task.task_id.value,))[0]['processing_status'] == 'cancelled'
    finally:
        connection.close()

def test_old_request_only_allows_readback_no_coordination_commands(http):
    from api.dependencies.service_start import build_service_start_application

    case, staff, _ = seed_case(http)
    dates = [{'original_date': '2027-01-05', 'new_date': '2027-02-10'}]
    request = seed_legacy_pending(case, staff[0][0], execution={'kind': 'leave-v1', 'decision': 'defer', 'dates': dates})
    candidate = write(
        'INSERT INTO scheduling_service_start_candidates '
        '(request_id,staff_id,proposed_start_date,proposed_end_date,willingness,interaction_hash) '
        "VALUES (%s,%s,'2027-01-05','2027-02-03','willing',%s)",
        (request, staff[1][0], '0' * 32 + uuid4().hex),
    )
    write('UPDATE scheduling_service_start_requests SET selected_candidate_id=%s,aggregate_version=5 WHERE id=%s',
          (candidate, request))
    date_changes = (('2027-01-05', '2027-02-10'),)
    commands = (
        ('inquire', 1, (staff[1][0], '2027-01-05', '2027-02-03', 1),
         {'staff_id': staff[1][0], 'start_date': '2027-01-05', 'end_date': '2027-02-03'}),
        ('invite', 2, (2,), {}),
        ('dates', 3, ('2027-02-10', 3, date_changes), {'start_date': '2027-02-10', 'date_changes': dates}),
        ('defer', 4, (date_changes, 4), {'dates': dates}),
    )
    connection = mysql_adapter.get_connection()
    keys = {}
    try:
        repository = build_service_start_application(connection).repository
        for operation, _, payload, _ in commands:
            keys[operation] = uuid4().hex
            repository.save_command(operation, keys[operation], request, (request, *payload, 'synthetic-union'))
        connection.commit()
    finally:
        connection.close()

    path = f'/api/v1/scheduling/service-start/{request}'
    old = checked(http.get(path))
    assert old['status'] == 'substitute_required'
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no':case}))['total'] == 0
    before = owner_state(case)
    candidates = rows('SELECT * FROM scheduling_service_start_candidates WHERE request_id=%s', (request,))
    deliveries = rows('SELECT COUNT(*) AS total FROM line_delivery_tasks')
    receipt_count_query = 'SELECT COUNT(*) AS total FROM admin_command_receipts WHERE command_family LIKE %s'
    receipt_count_params = ('scheduling.service_start.%',)
    receipts = rows(receipt_count_query, receipt_count_params)
    for operation, version, _, fields in commands:
        command_path = f'{path}/{operation}'
        body = {'expected_version': version, 'idempotency_key': keys[operation], **fields}
        assert checked(http.post(command_path, json=body)) == old
        changed = http.post(command_path, json={**body, 'expected_version': old['version']})
        assert changed.status_code == 409
        assert changed.json()['detail']['error']['code'] == 'service_start_key_reused'
        response = http.post(command_path, json={**body, 'expected_version': old['version'],
                                                 'idempotency_key': uuid4().hex})
        assert response.status_code == 410
        code = 'leave_substitute_dates_retired' if operation == 'dates' else 'service_start_coordination_retired'
        assert response.json()['detail']['error']['code'] == code
    assert checked(http.get(path)) == old
    assert owner_state(case) == before
    assert rows('SELECT * FROM scheduling_service_start_candidates WHERE request_id=%s', (request,)) == candidates
    assert rows('SELECT COUNT(*) AS total FROM line_delivery_tasks') == deliveries
    assert rows(receipt_count_query, receipt_count_params) == receipts

def test_multisegment_conflict_preserves_prior_peer_confirmation(http):
    case, staff, segments = seed_case(http, count=2)
    first = checked(submit(http, case, staff[0], segments[0])[0])
    assert first['status'] == 'awaiting_peers'
    write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) "
          "VALUES (%s,'long_leave','2027-02-04','2027-02-04','effective','synthetic','synthetic')", (staff[1][0],))
    before = owner_state(case)
    response, _ = submit(http, case, staff[1], segments[1], start='2027-02-04')
    assert response.status_code == 409
    assert owner_state(case) == before
    assert checked(http.get(f"/api/v1/scheduling/service-start/{first['request_id']}"))['status'] == 'awaiting_peers'

def test_legacy_dates_same_key_replays_completed_receipt_only(http):
    from api.dependencies.service_start import build_service_start_application

    case, staff, segments = seed_case(http)
    item = checked(submit(http, case, staff[0], segments[0])[0])
    key = uuid4().hex
    version = item['version'] - 1
    connection = mysql_adapter.get_connection()
    try:
        repository = build_service_start_application(connection).repository
        repository.save_command('dates', key, item['request_id'],
                                (item['request_id'], '2027-01-05', version, 'synthetic-union'))
        connection.commit()
    finally:
        connection.close()
    before = owner_state(case)
    path = f"/api/v1/scheduling/service-start/{item['request_id']}/dates"
    body = {'start_date':'2027-01-05', 'expected_version':version, 'idempotency_key':key}
    assert checked(http.post(path, json=body)) == item
    assert http.post(path, json={**body, 'idempotency_key':uuid4().hex}).status_code == 410
    assert owner_state(case) == before

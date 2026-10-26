"""Disposable MySQL: multi-caregiver -> substitution/handover -> bank -> completion.

The initial in-service schedule is an explicit synthetic execution fixture. All
subsequent schedule changes, receipts, payouts and completion use public APIs.
No product lifespan or provider delivery worker is started.
"""
from argparse import Namespace
from datetime import date, datetime, timedelta
from io import BytesIO
import os

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.mysql import mysql_adapter

DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires disposable localhost MySQL")


@pytest.fixture(scope="module")
def client():
    assert DATABASE.startswith("lu_test_") and os.environ["APP_ENV"] == "development"
    assert os.environ["LABOR_UNION_TEST_MYSQL_HOST"] in {"localhost", "127.0.0.1"}
    from scripts.bootstrap_disposable_mysql_schema import bootstrap
    target = DATABASE + "_complex"
    bootstrap(Namespace(host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"], port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=target, confirm_database=target))
    from api.dependencies import admin_auth
    from api.routes.finance_import import router as bank
    from api.routes.order_intake_terms_bootstrap import router as intake
    from api.routes.order_auto_completion import router as completion
    from api.routes.leave_substitution import router as leave
    from api.routes.finance_reports import router as reports
    from subsystems.access.authentication_session import AdminPrincipal
    app = FastAPI()
    for router in (bank, intake, completion, leave, reports):
        app.include_router(router)
    principal = AdminPrincipal(1, "complex-test", "Synthetic", "system_admin")
    for name in ("require_admin", "require_system_admin", "require_persisted_admin"):
        app.dependency_overrides[getattr(admin_auth, name)] = lambda: principal
    from api.dependencies.leave_substitution import get_leave_substitution_application
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    def fixed_leave_application():
        for application in get_leave_substitution_application():
            clock = FixedBusinessClock(datetime(2026, 10, 22, 10, tzinfo=TAIPEI_TIME_ZONE))
            application.workflow._clock = clock
            application.workflow._orders_port._clock = clock
            yield application
    app.dependency_overrides[get_leave_substitution_application] = fixed_leave_application
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG, "database", target)
        # Disposable table bootstrap excludes NAS runtime procedures. Install the
        # existing project-owned mutation used by real Scheduling replacements.
        from infrastructure.mysql.nas_mutations import PROCEDURES
        connection = mysql_adapter.get_connection()
        try:
            parameters, body, _ = PROCEDURES["lu_nas_cancel_occupancy_v1"]
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE PROCEDURE lu_nas_cancel_occupancy_v1 ({parameters}) SQL SECURITY INVOKER BEGIN {body} END")
            connection.commit()
        finally:
            connection.close()
        with TestClient(app, headers={"X-Correlation-ID": "complex-accounting-test"}) as http:
            yield http


def rows(sql, args=()):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, args)
            return list(cursor.fetchall())
    finally:
        connection.close()


def seed_case(client, case):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as c:
            c.execute("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic complex service','一般市民','連續服務','2026-09-01')", (case,))
            c.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,'2026-10-01',30,8,0,'08:00:00','17:00:00',0)", (case, c.lastrowid))
        connection.commit()
    finally:
        connection.close()
    url = f"/api/v1/orders/{case}/intake-completion"
    preview = checked(client.post(url + "/preview", json={}))
    checked(client.post(url + "/apply", json={"expected_lifecycle_version": preview["lifecycle_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": ""}, headers={"Idempotency-Key": case + ":intake"}))
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as c:
            staff = []
            for name in ("A", "B", "C"):
                c.execute("INSERT INTO staff(name,status) VALUES (%s,'active')", ("Synthetic " + case + " " + name,))
                staff.append(c.lastrowid)
                c.execute("INSERT INTO staff_bank_accounts(staff_id,is_primary,bank_code,account_no) VALUES (%s,1,'synthetic',%s)", (c.lastrowid, staff_account(staff[-1])))
            c.execute("INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) VALUES (%s,1,1,'effective',1,'synthetic','in-service fixture')", (case,))
            generation = c.lastrowid
            c.execute("UPDATE scheduling_aggregates SET effective_generation_id=%s,generation_counter=1,aggregate_version=1 WHERE case_no=%s", (generation, case))
            for index, staff_id in enumerate(staff[:2]):
                start = date(2026, 10, 1) + timedelta(days=index * 15)
                end = start + timedelta(days=14)
                c.execute("INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status) VALUES (%s,%s,%s,%s,%s,%s,%s,'active')", (case, generation, f"{case}:g1:a{index+1}", staff_id, index + 1, start, end))
                assignment = c.lastrowid
                c.execute("INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) VALUES (%s,'approved-rates-v1','citizen',300,'一般市民')", (assignment,))
                for offset in range(15):
                    day = start + timedelta(days=offset)
                    c.execute("INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,%s,1,0,1)", (case, staff_id, assignment, generation, day))
                    c.execute("INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) VALUES (%s,%s,%s,%s,'assignment_interval')", (staff_id, day, generation, assignment))
            c.execute("UPDATE orders SET status='服務中',actual_start_date='2026-10-01',actual_end_date='2026-10-30' WHERE case_no=%s", (case,))
        connection.commit()
        from api.dependencies.payroll_rebuild import build_payroll_rebuild_application
        from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
        from subsystems.payroll.rebuild_workflow import PayrollRebuildRequest
        application = build_payroll_rebuild_application(connection)
        preview = application.preview(case)
        application.apply(PayrollRebuildRequest(case, ExpectedVersion(preview.payroll_version), preview.fingerprint,
            IdempotencyKey(case + ":initial-payroll"), ActorContext("synthetic"), "", CorrelationId(case)))
        return staff
    finally:
        connection.close()


def checked(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()["data"]


def staff_account(staff):
    return "8" * 10 + str(staff).zfill(4)


def workbook(case, amount, sequence, *, account=None):
    headers = ['帳號','交易日','計息日','入帳日','摘要','幣別','支出','存入','餘額','銷帳編號','交易參考編號','','更正註記','存摺備註']
    day = f"2026/11/{sequence:02d}"
    virtual = f"99781699{int(case[:3]):03d}{int(case[3:]):03d}"
    row = ['1'*12,day+' 09:08:07',day,day,'轉帳','TWD',amount if account else None,None if account else amount,200000+int(case[3:])*100+sequence,None if account else virtual,account or f'{case}:{sequence}','synthetic',None,'fixture']
    out = BytesIO()
    pd.DataFrame([headers,row]).to_excel(out,sheet_name='來源',index=False,header=False)
    return out.getvalue()


def bank(client, case, amount, sequence, *, account=None):
    contents = workbook(case, amount, sequence, account=account)
    batch = checked(client.post('/api/v1/finance-import/workbooks/ingest', files={'workbook': (f'{case}-{sequence}.xlsx', contents, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}, headers={'Idempotency-Key': f'{case}:ingest:{sequence}'}))['batch_identity']
    plan = checked(client.post('/api/v1/finance-import/batches/preview', json={'batch_identity': batch}))
    assert plan['apply_allowed'] and plan['counts']['ready_dispatch'] == 1, plan
    body = {'batch_identity': batch, 'expected_batch_version': plan['batch_version'], 'preview_fingerprint': plan['preview_fingerprint'], 'reason': ''}
    accepted = checked(client.post('/api/v1/finance-import/batches/apply', json=body, headers={'Idempotency-Key': f'{case}:bank:{sequence}'}), 202)
    from api.dependencies.durable_job_handlers import finance_import_batch_apply_handler
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    connection = mysql_adapter.get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(connection), connection, {'finance_import_batch_apply': finance_import_batch_apply_handler}, 'complex-service-test')
        assert worker.recover_and_run_once()
    finally:
        connection.close()
    outcome = checked(client.get(f"/api/v1/finance-import/jobs/{accepted['job_id']}/batch-outcome"))
    assert outcome['status'] == 'succeeded' and outcome['receipt']['reconciled_count'] == 1, outcome
    replay = checked(client.post('/api/v1/finance-import/batches/apply', json=body, headers={'Idempotency-Key': f'{case}:bank:{sequence}'}), 202)
    assert replay['job_id'] == accepted['job_id']


def money_snapshot(case):
    return rows("SELECT o.staff_id,o.obligation_identity,o.obligation_kind,o.amount_due_ntd,o.status,COALESCE(p.balance_ntd,o.amount_due_ntd) AS balance_ntd,p.status AS projection_status FROM staff_obligations o LEFT JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity WHERE o.case_no=%s ORDER BY o.obligation_identity", (case,))


def change_body(client, case, staff, scenario):
    assignments = checked(client.get(f'/api/v1/orders/{case}/leave-substitution/assignments'))
    source = next(item for item in assignments if item['staff_id'] == staff[1])
    days = [day for day in source['official_schedules'] if day['work_date'] >= '2026-10-22'] if scenario == 'handover' else [day for day in source['official_schedules'] if day['work_date'] == '2026-10-24']
    body = {'original_assignment_id': source['assignment_id'], 'items': [{'original_schedule_id': day['schedule_id'], 'work_date': day['work_date'], 'resolution_type': 'substitute', 'substitute_staff_id': staff[2], 'is_double_pay': day['is_double_pay']} for day in days]}
    if scenario == 'handover':
        body['handover_date'] = '2026-10-22'
    return body


@pytest.mark.parametrize('scenario,paid', [('multi', False), ('substitute', False), ('handover', False), ('handover', True)])
def test_complex_service_updates_each_caregiver_and_preserves_received_money(client, scenario, paid):
    serial = rows("SELECT COUNT(*) AS count FROM orders")[0]['count'] + 1
    case = f"116{serial:06d}"
    staff = seed_case(client, case)
    initial = money_snapshot(case)
    assert sorted(int(row['balance_ntd']) for row in initial) == [36000, 36000]
    for sequence, amount in enumerate((12000, 36000, 24000), 1):
        bank(client, case, amount, sequence)
    receipts_before = rows("SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type='receipt' ORDER BY id", (case,))
    if paid:
        bank(client, case, 36000, 4, account=staff_account(staff[1]))
        assert next(row for row in money_snapshot(case) if row['staff_id'] == staff[1])['balance_ntd'] == 0
    if scenario != 'multi':
        body = change_body(client, case, staff, scenario)
        before = money_snapshot(case)
        plan = checked(client.post(f'/api/v1/orders/{case}/leave-substitution/preview', json=body))
        assert money_snapshot(case) == before
        assert plan['apply_readiness']['status'] == 'ready', plan
        body.update({f'expected_{owner}_version': plan[f'{owner}_version'] for owner in ('order', 'scheduling', 'client_finance', 'payroll')})
        body.update(preview_fingerprint=plan['preview_fingerprint'], reason='')
        headers = {'Idempotency-Key': case + ':change'}
        checked(client.post(f'/api/v1/orders/{case}/leave-substitution/apply', json=body, headers=headers))
        saved = money_snapshot(case)
        checked(client.post(f'/api/v1/orders/{case}/leave-substitution/apply', json=body, headers=headers))
        assert money_snapshot(case) == saved
    url = f'/api/v1/orders/{case}/service-completion'
    plan = checked(client.post(url + '/preview', json={'evaluation_at': '2026-11-01T00:00:00+08:00'}))
    body = {'evaluation_at': plan['evaluation_at'], 'expected_order_version': plan['expected_order_version'], 'preview_fingerprint': plan['fingerprint'], 'reason': ''}
    checked(client.post(url + '/apply', json=body, headers={'Idempotency-Key': case + ':complete'}))
    final = money_snapshot(case)
    active = {item['staff_id']: max(0, int(item['balance_ntd'])) for item in final if item['obligation_kind'] == 'service_pay' and item['status'] != 'cancelled' and item['projection_status'] != 'closed'}
    expected = {staff[0]: 36000, staff[1]: 36000} if scenario == 'multi' else {staff[0]: 36000, staff[1]: 33600, staff[2]: 2400} if scenario == 'substitute' else {staff[0]: 36000, staff[1]: 0 if paid else 14400, staff[2]: 21600}
    assert active == expected, final
    cash = checked(client.get('/api/v1/finance-reports/accounts-payable/cash-requirements'))
    staff_rows = [row for row in cash['rows'] if row['case_no'] == case and row['payment_type'] == 'staff_payable']
    assert {row['staff_id']: row['unpaid_amount_ntd'] for row in staff_rows} == expected
    if paid:
        assert rows("SELECT remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s", (staff[1],)) == [{'remaining_amount_ntd': 21600}]
        assert rows("SELECT COUNT(*) AS count FROM staff_payout_obligation_links link JOIN staff_obligations obligation ON obligation.obligation_identity=link.obligation_identity WHERE obligation.case_no=%s", (case,)) == [{'count': 1}]
    assert rows("SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type='receipt' ORDER BY id", (case,)) == receipts_before
    ownership = rows("SELECT staff_id,COUNT(*) AS days FROM staff_schedule WHERE case_no=%s AND effective_marker=1 AND is_work_day=1 GROUP BY staff_id", (case,))
    assert sum(item['days'] for item in ownership) == 30
    assert rows("SELECT status FROM orders WHERE case_no=%s", (case,)) == [{'status': '訂單完成'}]

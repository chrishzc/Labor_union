"""Synthetic localhost evidence through real HTTP, writers and MySQL transactions."""

from argparse import Namespace
from datetime import date, timedelta
import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql
import pytest

from api.dependencies.admin_auth import require_system_admin
from api.routes.accounting_pricing import router as pricing_router
from api.routes.case_architecture_bootstrap import router as bootstrap_router
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.pricing_configuration_repository import bind_initial_pricing
from infrastructure.mysql.case_category_query import CASE_CATEGORY_SQL
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.access.authentication_session import AdminPrincipal

pytestmark = pytest.mark.skipif(os.getenv("PRICING_MYSQL") != "1", reason="explicit disposable localhost pricing qualification")


@pytest.fixture(scope="module")
def database():
    config = mysql_adapter._database_config_from_environment()
    assert config["host"] in {"127.0.0.1", "localhost"}
    assert os.getenv("APP_ENV", "development") == "development"
    name = "lu_test_pricing_" + uuid4().hex[:12]
    bootstrap(Namespace(**{key: config[key] for key in ("host", "port", "user", "password")}, database=name, confirm_database=name))
    old = mysql_adapter.DB_CONFIG.copy()
    mysql_adapter.DB_CONFIG.update({**config, "database": name})
    try:
        yield name
    finally:
        mysql_adapter.DB_CONFIG.clear()
        mysql_adapter.DB_CONFIG.update(old)
        assert name.startswith("lu_test_pricing_")
        server = {key: value for key, value in config.items() if key != "database"}
        connection = pymysql.connect(**server)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{name}`")
        connection.close()


@pytest.fixture(scope="module")
def client(database):
    app = FastAPI()
    app.include_router(pricing_router)
    app.include_router(bootstrap_router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(id=None, username="pricing-test", display_name="Synthetic pricing test", role="system_admin")
    with TestClient(app) as client:
        yield client


def post(client, path, body, key):
    response = client.post(path, json=body, headers={"Idempotency-Key": key, "X-Correlation-ID": key})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def policy():
    def identity(name, rule, cap, rate, excess=None):
        return {"identity_name": name, "rule": rule, "subsidy_hours": cap,
            "client": {"covered": rate, "excess": excess or rate}, "payroll": {"covered": rate, "excess": excess or rate}}
    return {"effective_on": (date.today() - timedelta(days=1)).isoformat(),
        "identities": [identity("補助市民", "citizen", 40, 300), identity("社福", "social", 120, 350, 300), identity("非市民", "non_citizen", 0, 320), identity("新增社福身分", "social", 100, 340, 290)],
        "twins_client": {"covered": 450, "excess": 400}, "twins_payroll": {"covered": 460, "excess": 410}}


def seed_case(case_no, identity="社福"):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES(%s,'Synthetic Pricing Client',%s,'連續服務','2026-10-01')", (case_no, identity))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,requires_cooking,service_start_time,service_end_time,service_end_day_offset) VALUES(%s,%s,'洽談中',0,'2026-10-01',20,8,0,0,'09:00:00','17:00:00',0)", (case_no, client_id))
            cursor.execute("INSERT INTO beclass_records(bound_case_no,record_origin,survey_details) VALUES(%s,'admin_manual',%s)", (case_no, '{"特殊計費:胎數":"單胞胎"}'))
            bind_initial_pricing(cursor, case_no)
        connection.commit()
    finally:
        connection.close()


def bootstrap_case(client, case_no):
    status = client.get(f"/api/v1/cases/{case_no}/architecture-bootstrap/status")
    assert status.status_code == 200, status.text
    data = status.json()["data"]
    # The canonical bootstrap recommendation is intentionally obtained from its owner.
    intent = data["recommendation"]
    preview = post(client, f"/api/v1/cases/{case_no}/architecture-bootstrap/preview", intent, f"{case_no}-preview")
    body = {**intent, "expected_order_version": preview["order_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "synthetic pricing fixture"}
    post(client, f"/api/v1/cases/{case_no}/architecture-bootstrap/apply", body, f"{case_no}-bootstrap")


def test_policy_replay_conflict_case_binding_and_manual_http_flow(client):
    seed_case("pricing-legacy")
    seed_case("opaque-legacy-case", identity="非市民")
    body = {"policy": policy(), "expected_revision": 0}
    assert post(client, "/api/v1/accounting-pricing/policies", body, "pricing-policy-one")["revision"] == 1
    assert client.get('/api/v1/accounting-pricing').json()['data']['versions'][0]['reason'] == ''
    assert post(client, "/api/v1/accounting-pricing/policies", body, "pricing-policy-one")["revision"] == 1
    stale = client.post("/api/v1/accounting-pricing/policies", json=body, headers={"Idempotency-Key": "pricing-policy-stale"})
    assert stale.status_code == 409
    seed_case("pricing-new")
    bootstrap_case(client, "pricing-new")
    value = client.get("/api/v1/accounting-pricing/cases/pricing-new")
    assert value.status_code == 200, value.text
    current = value.json()["data"]
    assert current["source"] == "policy"
    assert current["impact"]["client_amount"] == 12000
    assert current["impact"]["staff_total_amount"] == 54000
    terms = {**current["terms"], "client": {"covered": 350, "excess": 280}, "payroll": {"covered": 360, "excess": 310}}
    request = {"terms": terms, "expected_revision": 0}
    preview = post(client, "/api/v1/accounting-pricing/cases/pricing-new/preview", request, "pricing-preview")
    assert preview["after"]["client_amount"] == 11200
    assert preview["after"]["subsidy_amount"] == 43200
    apply = {**request, "preview_fingerprint": preview["preview_fingerprint"], "reason": "synthetic per-case correction"}
    assert post(client, "/api/v1/accounting-pricing/cases/pricing-new/apply", apply, "pricing-case-one")["revision"] == 1
    assert post(client, "/api/v1/accounting-pricing/cases/pricing-new/apply", apply, "pricing-case-one")["revision"] == 1
    after = client.get("/api/v1/accounting-pricing/cases/pricing-new").json()["data"]
    assert after["source"] == "manual" and after["terms"] == terms
    connection = mysql_adapter.get_connection()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pricing_policy_id FROM orders WHERE case_no='pricing-legacy'")
        assert cursor.fetchone()["pricing_policy_id"] is None
        cursor.execute("SELECT COUNT(*) AS n FROM case_pricing_events WHERE case_no='pricing-new'")
        assert cursor.fetchone()["n"] == 1
        cursor.execute(f"SELECT o.case_no,{CASE_CATEGORY_SQL} AS category FROM orders o "
            "JOIN clients c ON c.id=o.client_id WHERE o.case_no IN ('pricing-new','opaque-legacy-case')")
        assert {row['case_no']: row['category'] for row in cursor.fetchall()} == {
            'pricing-new': 'subsidy', 'opaque-legacy-case': 'non_citizen',
        }
    connection.close()


def test_direct_case_save_without_preview_or_reason_commits_once(client):
    case_no = 'pricing-direct-save'
    seed_case(case_no)
    bootstrap_case(client, case_no)
    current = client.get(f'/api/v1/accounting-pricing/cases/{case_no}').json()['data']
    candidate = {**current['terms'], 'client': {**current['terms']['client'], 'excess': 285}}
    body = {'terms': candidate, 'expected_revision': current['revision']}
    path = f'/api/v1/accounting-pricing/cases/{case_no}/apply'
    assert post(client, path, body, 'direct-save-blank')['revision'] == current['revision'] + 1
    assert post(client, path, body, 'direct-save-blank')['revision'] == current['revision'] + 1
    after = client.get(f'/api/v1/accounting-pricing/cases/{case_no}').json()['data']
    assert after['terms'] == candidate and after['source'] == 'manual'
    stale = client.post(path, json=body, headers={'Idempotency-Key': 'direct-save-stale'})
    assert stale.status_code == 409
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT reason FROM case_pricing_events WHERE case_no=%s', (case_no,))
            assert cursor.fetchall() == [{'reason': ''}]
    finally:
        connection.close()


def seed_assignment(case_no):
    """Fixture-only official service facts; salary still goes through its owner writer."""
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO staff(name) VALUES('Synthetic Pricing Staff')")
            staff_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff_bank_accounts(staff_id,bank_code,account_no,is_primary) VALUES(%s,'012',%s,1)", (staff_id, '0' * 12))
            cursor.execute("INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) VALUES(%s,1,1,'effective',1,'pricing-test','synthetic fixture')", (case_no,))
            generation_id = cursor.lastrowid
            cursor.execute("UPDATE scheduling_aggregates SET aggregate_version=1,generation_counter=1,effective_generation_id=%s WHERE case_no=%s", (generation_id, case_no))
            cursor.execute("INSERT INTO case_staff_assignments(case_no,generation_id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status) VALUES(%s,%s,%s,1,'2026-10-01','2026-10-20','active')", (case_no, generation_id, staff_id))
            assignment_id = cursor.lastrowid
            cursor.execute("INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) SELECT %s,policy_version,policy_kind,hourly_rate_ntd,source_identity_status FROM case_payroll_rate_policy_snapshots WHERE case_no=%s", (assignment_id, case_no))
            cursor.executemany("INSERT INTO staff_schedule(case_no,generation_id,assignment_id,staff_id,work_date,is_work_day,effective_marker) VALUES(%s,%s,%s,%s,%s,1,1)", [(case_no,generation_id,assignment_id,staff_id,date(2026,10,day)) for day in range(1,21)])
            cursor.execute("UPDATE orders SET actual_end_date='2026-10-20' WHERE case_no=%s", (case_no,))
        connection.commit()
    finally:
        connection.close()
    return staff_id


def test_real_salary_writer_installments_export_and_repricing(client):
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository
    from infrastructure.mysql.accounts_payable_export_sources import MySqlStaffPayableExportSource
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow
    from shared_kernel.identities import ActorContext, IdempotencyKey, CorrelationId

    seed_case('pricing-scheduled')
    bootstrap_case(client, 'pricing-scheduled')
    staff_id = seed_assignment('pricing-scheduled')
    connection = mysql_adapter.get_connection()
    try:
        repository = MySqlPayrollRebuildRepository(connection)
        with MySqlUnitOfWork(connection) as unit:
            PayrollRebuildWorkflow(repository, None).synchronize_in_unit_of_work('pricing-scheduled', actor=ActorContext('pricing-test'), key=IdempotencyKey('pricing-salary'), correlation_id=CorrelationId('pricing-salary'))
            unit.commit()
        source = MySqlStaffPayableExportSource(connection)
        assert [item.amount.amount for item in source.load(date(2026,11,15)) if item.staff_id == staff_id] == [12000]
        assert [item.amount.amount for item in source.load(date(2026,12,15)) if item.staff_id == staff_id] == [42000]
        assert repository.query_staff_month(staff_id,2026,11).payable_total.amount == 12000
        assert repository.query_staff_month(staff_id,2026,12).payable_total.amount == 42000
        audit = source.load_case('pricing-scheduled',date(2026,11,15))
        assert len(audit) == 2
        assert sum(item.amount_due.amount for item in audit) == 54000
        connection.rollback()

        current = client.get('/api/v1/accounting-pricing/cases/pricing-scheduled').json()['data']
        terms = {**current['terms'], 'payroll': {'covered':360,'excess':310}}
        request = {'terms':terms,'expected_revision':current['revision']}
        preview = post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/preview',request,'scheduled-preview')
        apply = {**request,'preview_fingerprint':preview['preview_fingerprint'],'reason':'synthetic scheduled repricing'}
        post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/apply',apply,'scheduled-apply')
        assert [item.amount.amount for item in source.load(date(2026,11,15)) if item.staff_id == staff_id] == [12400]
        assert [item.amount.amount for item in source.load(date(2026,12,15)) if item.staff_id == staff_id] == [43200]
        from infrastructure.mysql.staff_payout_repository import _query_obligation_rows
        with connection.cursor() as cursor:
            assert _query_obligation_rows(cursor,staff_id)[0]['due_date'] == '2026-11-15'
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM staff_obligations WHERE case_no='pricing-scheduled' AND obligation_kind='service_pay' AND status<>'cancelled'")
            assert cursor.fetchone()['n'] == 1
            cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no='pricing-scheduled' AND obligation_kind='service_pay' AND status<>'cancelled'")
            identity = cursor.fetchone()['obligation_identity']
            cursor.execute("INSERT INTO staff_payable_accounts(staff_id,aggregate_version) VALUES(%s,1) ON DUPLICATE KEY UPDATE aggregate_version=1",(staff_id,))
            cursor.execute("INSERT INTO staff_payout_events(staff_id,event_type,amount_ntd,occurred_on,bank_account_identity_hash,reconciliation_reference,idempotency_key,actor,reason) VALUES(%s,'payout',12400,'2026-11-15',%s,'pricing-synthetic-paid','pricing-synthetic-paid','pricing-test','immutable synthetic payout fixture')",(staff_id,'a'*64))
            payout_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff_payout_obligation_links(payout_event_id,obligation_identity,allocated_amount_ntd,allocation_ordinal) VALUES(%s,%s,12400,1)",(payout_id,identity))
            from infrastructure.mysql.staff_payout_repository import _projection_rows, _upsert_projection
            _upsert_projection(cursor,_projection_rows(cursor,(identity,))[0],1)
        connection.commit()
        assert not [item for item in source.load(date(2026,11,15)) if item.staff_id == staff_id]
        assert [item.amount.amount for item in source.load(date(2026,12,15)) if item.staff_id == staff_id] == [43200]
        with connection.cursor() as cursor:
            assert _query_obligation_rows(cursor,staff_id)[0]['due_date'] == '2026-12-15'
        connection.rollback()
        current = client.get('/api/v1/accounting-pricing/cases/pricing-scheduled').json()['data']
        request = {'terms':{**current['terms'],'payroll':{'covered':340,'excess':300}},'expected_revision':current['revision']}
        preview = post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/preview',request,'paid-preview')
        apply = {**request,'preview_fingerprint':preview['preview_fingerprint'],'reason':'synthetic paid correction'}
        post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/apply',apply,'paid-apply')
        assert not [item for item in source.load(date(2026,11,15)) if item.staff_id == staff_id]
        assert [item.amount.amount for item in source.load(date(2026,12,15)) if item.staff_id == staff_id] == [40400]
        with connection.cursor() as cursor:
            cursor.execute('SELECT amount_ntd FROM staff_payout_events WHERE id=%s',(payout_id,))
            assert cursor.fetchone()['amount_ntd'] == 12400
            cursor.execute('SELECT amount_due_ntd FROM staff_obligations WHERE obligation_identity=%s',(identity,))
            assert cursor.fetchone()['amount_due_ntd'] == 55600
    finally:
        connection.close()


def test_new_identity_inherits_existing_give_and_deposit_rules(client):
    seed_case('pricing-new-identity','新增社福身分')
    bootstrap_case(client,'pricing-new-identity')
    response = client.get('/api/v1/accounting-pricing/cases/pricing-new-identity')
    assert response.status_code == 200, response.text
    current = response.json()['data']
    assert current['terms']['rule'] == 'social'
    assert current['impact']['client_amount'] == 60 * 290
    assert current['impact']['staff_total_amount'] == 100 * 340 + 60 * 290


def test_owner_failure_rolls_back_every_repricing_write_and_original_key_can_retry(client,monkeypatch):
    import infrastructure.mysql.payroll_terms_writer as payroll_writer
    case_no = 'pricing-scheduled'
    current = client.get(f'/api/v1/accounting-pricing/cases/{case_no}').json()['data']
    request = {'terms':{**current['terms'],'client':{'covered':350,'excess':290}},'expected_revision':current['revision']}
    preview = post(client,f'/api/v1/accounting-pricing/cases/{case_no}/preview',request,'rollback-preview')
    apply = {**request,'preview_fingerprint':preview['preview_fingerprint'],'reason':'synthetic atomic rollback'}
    def fail_after_finance(*args):
        raise ValueError('synthetic_owner_failure')
    with monkeypatch.context() as patch:
        patch.setattr(payroll_writer,'persist_payroll_terms_impact',fail_after_finance)
        response = client.post(f'/api/v1/accounting-pricing/cases/{case_no}/apply',json=apply,headers={'Idempotency-Key':'rollback-apply'})
        assert response.status_code == 422, response.text
    after = client.get(f'/api/v1/accounting-pricing/cases/{case_no}').json()['data']
    assert after == current
    post(client,f'/api/v1/accounting-pricing/cases/{case_no}/apply',apply,'rollback-apply')


def test_settled_subsidy_is_a_typed_zero_write_blocker(client):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,direction,bank_references,warnings,raw_payload) VALUES(%s,'taishin','incoming','{}','[]','{}')",('b'*64,))
            bank_id = cursor.lastrowid
            cursor.execute("INSERT INTO government_subsidy_period_entries(period_unit,period_year,period_index,period_start,period_end,finance_import_row_id,amount_ntd,paid_on,idempotency_key,actor) VALUES('month',2026,10,'2026-10-01','2026-11-01',%s,40800,'2026-12-15','pricing-subsidy-fixture','pricing-test')",(bank_id,))
            cursor.execute("INSERT INTO government_subsidy_period_members(receipt_id,case_no,service_end_date,amount_ntd) VALUES(%s,'pricing-scheduled','2026-10-20',40800)",(cursor.lastrowid,))
        connection.commit()
    finally:
        connection.close()
    current = client.get('/api/v1/accounting-pricing/cases/pricing-scheduled').json()['data']
    request = {'terms':{**current['terms'],'payroll':{'covered':341,'excess':300}},'expected_revision':current['revision']}
    preview = post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/preview',request,'settled-preview')
    apply = {**request,'preview_fingerprint':preview['preview_fingerprint'],'reason':'must block settled subsidy'}
    response = client.post('/api/v1/accounting-pricing/cases/pricing-scheduled/apply',json=apply,headers={'Idempotency-Key':'settled-apply'})
    assert response.status_code == 409, response.text
    assert 'case_pricing_settled_subsidy_correction_required' in response.text
    assert client.get('/api/v1/accounting-pricing/cases/pricing-scheduled').json()['data'] == current


def test_effective_day_taiwan_midnight_and_pending_case_keeps_first_binding(client,monkeypatch):
    from datetime import datetime, timezone
    import infrastructure.mysql.pricing_configuration_repository as pricing_repository
    catalog = client.get('/api/v1/accounting-pricing').json()['data']
    future = policy()
    future['effective_on'] = '2030-01-02'
    future['identities'][1]['subsidy_hours'] = 130
    post(client,'/api/v1/accounting-pricing/policies',{'policy':future,'expected_revision':catalog['revision'],'reason':'synthetic effective boundary'},'future-policy')
    class Clock(datetime):
        instant = datetime(2030,1,1,15,59,59,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz=None): return cls.instant
    monkeypatch.setattr(pricing_repository,'datetime',Clock)
    seed_case('pricing-pending-before')
    Clock.instant = datetime(2030,1,1,16,0,0,tzinfo=timezone.utc)
    seed_case('pricing-at-midnight')
    bootstrap_case(client,'pricing-pending-before')
    bootstrap_case(client,'pricing-at-midnight')
    before = client.get('/api/v1/accounting-pricing/cases/pricing-pending-before').json()['data']
    at = client.get('/api/v1/accounting-pricing/cases/pricing-at-midnight').json()['data']
    assert before['terms']['subsidy_hours'] == 120
    assert at['terms']['subsidy_hours'] == 130


def test_contract_estimate_and_government_projection_use_current_case_tiers(client):
    from infrastructure.mysql.contract_full_preview_repository import _extend_precontract_staff_payroll
    from infrastructure.mysql.order_government_subsidy_projection_repository import MySqlOrderGovernmentSubsidyProjectionRepository
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE name='Synthetic Pricing Staff'")
            staff_id = cursor.fetchone()['id']
        segment = {'id':1,'staff_id':staff_id}
        plan = {'segments':(segment,), 'allocations':tuple((segment,date(2026,10,day)) for day in range(1,21))}
        facts = {'identity_status':'新增社福身分','service_days':20,'service_hours_per_day':8,
            'total_hours':160,'floor_fee':0,'total_employer_self_pay_payable':17400}
        owners = {}
        _extend_precontract_staff_payroll(connection,'pricing-new-identity',facts,owners,plan,1)
        assert facts['staff_payable_total'] == 51400
        assert facts['service_unit_price'] == '補助內 340 元／時；用盡後 290 元／時'
        assert '17,400 元：2026-11-15' in facts['staff_payable_due_date']
        assert '34,000 元：2026-12-15' in facts['staff_payable_due_date']
        projected = MySqlOrderGovernmentSubsidyProjectionRepository(connection).query_order_projection_facts(('pricing-scheduled',))
        assert projected[0].estimated_subsidy_amount_ntd == 40800
    finally:
        connection.close()

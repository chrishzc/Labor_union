"""Synthetic localhost evidence through real HTTP, writers and MySQL transactions."""

from argparse import Namespace
from datetime import date, datetime, timedelta
from decimal import Decimal
import os
import json
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql
import pytest

from api.dependencies.admin_auth import require_system_admin
from api.routes.accounting_pricing import router as pricing_router
from api.routes.case_architecture_bootstrap import router as bootstrap_router
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.pricing_configuration_repository import bind_initial_pricing, CASE_PRICING_FACTS_SQL
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
        "identities": [identity("一般市民", "citizen", 40, 300), identity("補助市民", "social", 120, 350, 300), identity("非市民", "non_citizen", 0, 320), identity("新增補助市民身分", "social", 100, 340, 290)],
        "twins_client": {"covered": 450, "excess": 400}, "twins_payroll": {"covered": 450, "excess": 410}}


def seed_case(case_no, identity="補助市民"):
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
    seed_case("pricing-general", identity="一般市民")
    bootstrap_case(client, "pricing-new")
    value = client.get("/api/v1/accounting-pricing/cases/pricing-new")
    assert value.status_code == 200, value.text
    current = value.json()["data"]
    assert current["source"] == "policy"
    assert current["impact"]["client_amount"] == 12000
    assert current["impact"]["staff_total_amount"] == 54000
    terms = {**current["terms"], "client": {"covered": 360, "excess": 280}, "payroll": {"covered": 360, "excess": 310}}
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
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT case_no,pricing_rule,pricing_subsidy_hours FROM ({CASE_PRICING_FACTS_SQL}) pricing WHERE case_no IN ('pricing-new','pricing-general')")
            assert {row['case_no']: (row['pricing_rule'], int(Decimal(str(row['pricing_subsidy_hours'])))) for row in cursor.fetchall()} == {
                'pricing-new': ('social', 120), 'pricing-general': ('citizen', 40),
            }
            cursor.execute("SELECT pricing_policy_id FROM orders WHERE case_no='pricing-legacy'")
            assert cursor.fetchone()["pricing_policy_id"] is None
            cursor.execute("SELECT COUNT(*) AS n FROM case_pricing_events WHERE case_no='pricing-new'")
            assert cursor.fetchone()["n"] == 1
            cursor.execute(f"SELECT o.case_no,{CASE_CATEGORY_SQL} AS category FROM orders o "
                "JOIN clients c ON c.id=o.client_id WHERE o.case_no IN ('pricing-new','opaque-legacy-case')")
            assert {row['case_no']: row['category'] for row in cursor.fetchall()} == {
                'pricing-new': 'subsidy', 'opaque-legacy-case': 'non_citizen',
            }
            # Simulate an immutable historical binding; rollback this fixture-only snapshot.
            legacy = policy()
            legacy['identities'][0]['identity_name'] = '補助市民'
            legacy['identities'][1]['identity_name'] = '社福'
            cursor.execute("INSERT INTO accounting_pricing_policies(id,effective_on,policy_json,actor,reason,created_at_utc) VALUES(999,'2026-01-01',%s,'synthetic','legacy fixture',UTC_TIMESTAMP(6))", (json.dumps(legacy),))
            cursor.execute("UPDATE orders SET pricing_policy_id=999 WHERE case_no='pricing-general'")
            cursor.execute("UPDATE clients SET identity_status='補助市民' WHERE case_no='pricing-general'")
            from infrastructure.mysql.subsidy_return_query_repository import MySqlSubsidyReturnQueryRepository
            from subsystems.client_finance.subsidy_return_query import query_subsidy_returns
            repository = MySqlSubsidyReturnQueryRepository(connection)
            fact, = repository.query_facts(after_case_no=None, case_no='pricing-general', search=None, limit=2)
            assert fact.pricing.rule.value == 'citizen' and fact.pricing.subsidy_hours == 40
            refund, = query_subsidy_returns(repository, case_no='pricing-general').rows
            assert refund.amount_ntd == 12000
            assert not query_subsidy_returns(repository, case_no='pricing-new').rows
    finally:
        connection.rollback()
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
            cursor.execute("INSERT INTO staff_bank_accounts(staff_id,bank_code,account_no,is_primary) VALUES(%s,'012',%s,1)", (staff_id, f'{staff_id:012d}'))
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
        terms = {**current['terms'], 'client': {**current['terms']['client'], 'covered':360}, 'payroll': {'covered':360,'excess':310}}
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
            cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,debit,direction,bank_references,warnings,raw_payload,classification_type) VALUES(%s,'sinopac','2026-11-15',12400,'outgoing','{}','[]','{}','staff_payout')",(uuid4().hex + uuid4().hex,))
            bank_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff_payout_events(staff_id,event_type,amount_ntd,occurred_on,bank_account_identity_hash,reconciliation_reference,idempotency_key,actor,reason,finance_import_row_id) VALUES(%s,'payout',12400,'2026-11-15',%s,'pricing-synthetic-paid','pricing-synthetic-paid','pricing-test','immutable synthetic payout fixture',%s)",(staff_id,'a'*64,bank_id))
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
        request = {'terms':{**current['terms'],'client':{**current['terms']['client'],'covered':340},'payroll':{'covered':340,'excess':300}},'expected_revision':current['revision']}
        preview = post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/preview',request,'paid-preview')
        apply = {**request,'preview_fingerprint':preview['preview_fingerprint'],'reason':'synthetic paid correction'}
        post(client,'/api/v1/accounting-pricing/cases/pricing-scheduled/apply',apply,'paid-apply')
        # 自備款已超付，不能從未來補助款扣抵，兩個來源均須先核對。
        for payment_date in (date(2026,11,15), date(2026,12,15)):
            items = [item for item in source.load(payment_date) if item.staff_id == staff_id]
            assert [item.status.value for item in items] == ['anomaly']
        with connection.cursor() as cursor:
            cursor.execute('SELECT funding_kind,amount_ntd FROM staff_obligation_installments '
                           'WHERE obligation_identity=%s', (identity,))
            assert {row['funding_kind']: row['amount_ntd'] for row in cursor.fetchall()} == {
                'client': 12000, 'subsidy': 40800,
            }
            cursor.execute('SELECT amount_ntd FROM staff_payout_events WHERE id=%s',(payout_id,))
            assert cursor.fetchone()['amount_ntd'] == 12400
            cursor.execute('SELECT amount_due_ntd FROM staff_obligations WHERE obligation_identity=%s',(identity,))
            assert cursor.fetchone()['amount_due_ntd'] == 55600
    finally:
        connection.close()


def test_new_identity_inherits_existing_give_and_deposit_rules(client):
    seed_case('pricing-new-identity','新增補助市民身分')
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
    request = {'terms':{**current['terms'],'client':{**current['terms']['client'],'excess':290}},'expected_revision':current['revision']}
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
    request = {'terms':{**current['terms'],'client':{**current['terms']['client'],'covered':341},'payroll':{'covered':341,'excess':300}},'expected_revision':current['revision']}
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
        facts = {'identity_status':'新增補助市民身分','service_days':20,'service_hours_per_day':8,
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


def test_unequal_subsidy_case_and_policy_commands_are_zero_write_422(client):
    from copy import deepcopy
    case_no = 'pricing-subsidy-guard'
    seed_case(case_no)
    bootstrap_case(client, case_no)
    path = f'/api/v1/accounting-pricing/cases/{case_no}'
    current = client.get(path).json()['data']
    invalid = deepcopy(current['terms'])
    invalid['client']['covered'] += 1
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT (SELECT COUNT(*) FROM case_pricing_events) AS events,(SELECT COUNT(*) FROM accounting_pricing_receipts) AS receipts')
            before = cursor.fetchone()
        for suffix in ('preview', 'apply'):
            response = client.post(path + '/' + suffix, json={'terms': invalid, 'expected_revision': current['revision']}, headers={'Idempotency-Key': 'invalid-' + suffix})
            assert response.status_code == 422 and 'pricing_covered_rates_must_match' in response.text, response.text
        assert client.get(path).json()['data'] == current
        catalog = client.get('/api/v1/accounting-pricing').json()['data']
        for twin in (False, True):
            invalid_policy = policy()
            if twin:
                invalid_policy['twins_payroll']['covered'] += 1
            else:
                invalid_policy['identities'][0]['payroll']['covered'] += 1
            response = client.post('/api/v1/accounting-pricing/policies', json={'policy': invalid_policy, 'expected_revision': catalog['revision']}, headers={'Idempotency-Key': 'invalid-policy-' + str(twin)})
            assert response.status_code == 422 and 'pricing_covered_rates_must_match' in response.text, response.text
        assert client.get('/api/v1/accounting-pricing').json()['data'] == catalog
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute('SELECT (SELECT COUNT(*) FROM case_pricing_events) AS events,(SELECT COUNT(*) FROM accounting_pricing_receipts) AS receipts')
            assert cursor.fetchone() == before
    finally:
        connection.close()


def test_non_citizen_zero_subsidy_and_independent_self_pay_through_real_writers(client):
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow
    from shared_kernel.identities import ActorContext, IdempotencyKey, CorrelationId
    case_no = 'pricing-non-citizen-zero'
    seed_case(case_no, identity='非市民')
    bootstrap_case(client, case_no)
    staff_id = seed_assignment(case_no)
    connection = mysql_adapter.get_connection()
    try:
        repository = MySqlPayrollRebuildRepository(connection)
        with MySqlUnitOfWork(connection) as unit:
            PayrollRebuildWorkflow(repository, None).synchronize_in_unit_of_work(case_no, actor=ActorContext('pricing-test'), key=IdempotencyKey('nc-initial'), correlation_id=CorrelationId('nc-initial'))
            unit.commit()
        path = f'/api/v1/accounting-pricing/cases/{case_no}'
        current = client.get(path).json()['data']
        assert current['terms']['subsidy_hours'] == current['terms']['client']['covered'] == current['terms']['payroll']['covered'] == 0
        candidate = {**current['terms'], 'client': {'covered': 0, 'excess': 330}, 'payroll': {'covered': 0, 'excess': 310}}
        post(client, path + '/apply', {'terms': candidate, 'expected_revision': current['revision']}, 'nc-direct-save')
        after = client.get(path).json()['data']
        assert after['terms'] == candidate
        assert all(after['impact'][key] == 0 for key in ('covered_hours', 'staff_covered_amount', 'subsidy_amount', 'subsidy_return_amount'))
        assert (after['impact']['client_amount'], after['impact']['staff_total_amount']) == (52800, 49600)
        assert repository.query_staff_month(staff_id, 2026, 11).payable_total.amount == 49600
        assert repository.query_staff_month(staff_id, 2026, 12).payable_total.amount == 0
    finally:
        connection.close()


def test_deposit_policy_round_trips_and_binds_new_hcm_cases(client):
    from api.dependencies.case_import import build_case_import_application
    from infrastructure.mysql.pricing_configuration_repository import initial_identity_rule
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.case_import.case_import_workflow import ApplyCaseImport
    from subsystems.case_import.hcm_adapter import build_hcm_case_import_intent

    def publish(days, *, legacy=False):
        draft = policy()
        draft["identities"].append({
            **draft["identities"][1], "identity_name": "原住民", "subsidy_hours": 80,
            "client": {"covered": 350, "excess": 350},
        })
        if legacy:
            draft["indigenous_deposit_service_days"] = days
        else:
            draft["identities"][-1]["deposit_service_days"] = days
            draft["identities"][0]["deposit_service_days"] = 2
        before = client.get("/api/v1/accounting-pricing").json()["data"]["revision"]
        saved = post(client, "/api/v1/accounting-pricing/policies",
                     {"policy": draft, "expected_revision": before}, f"indigenous-policy-{days}")
        current = client.get("/api/v1/accounting-pricing").json()["data"]["versions"][0]
        assert current["revision"] == saved["revision"]
        if legacy:
            assert current["policy"]["indigenous_deposit_service_days"] == days
        else:
            assert current["policy"]["identities"][-1]["deposit_service_days"] == days
            assert current["policy"]["identities"][0]["deposit_service_days"] == 2
        return saved["revision"]

    start = date(2026, 11, 16)

    def import_case(case_no, service_days, identity="原住民"):
        connection = mysql_adapter.get_connection()
        try:
            with connection.cursor() as cursor:
                rule = initial_identity_rule(cursor, identity, case_no)
            intent = build_hcm_case_import_intent({
                "case_no": case_no, "name": f"Synthetic {case_no}", "identity_status": identity,
                "created_at": datetime(2026, 11, 1), "service_start_date": start,
                "service_days": service_days, "service_time": "8小時 09:00-17:00",
                "service_type": "連續服務",
            }, start + timedelta(days=service_days - 1), pricing_identity_rule=rule)
            workflow = build_case_import_application(connection)
            correlation = CorrelationId(f"indigenous-import:{case_no}")
            preview = workflow.preview(intent, correlation)
            workflow.apply(ApplyCaseImport(intent, ExpectedVersion(0), preview.fingerprint,
                IdempotencyKey(correlation.value), ActorContext("pricing-test"), "synthetic deposit fixture", correlation))
        finally:
            connection.close()

    zero_policy = publish(0, legacy=True)
    import_case("115009911", 20)
    five_policy = publish(5)
    import_case("115009912", 31)
    import_case("115009913", 10)
    import_case("115009914", 20, "一般市民")
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            for case_no, revision, days, amounts in (
                ("115009911", zero_policy, 0, {"first": 28000}),
                ("115009912", five_policy, 5, {"deposit": 14000, "first": 42000, "second": 2800}),
                ("115009913", five_policy, 5, {}),
                ("115009914", five_policy, 2, {"deposit": 4800, "first": 36000, "second": 7200}),
            ):
                cursor.execute("SELECT o.pricing_policy_id,t.deposit_service_days,t.second_payment_due_date "
                    "FROM orders o JOIN client_payment_terms t ON t.case_no=o.case_no WHERE o.case_no=%s", (case_no,))
                terms = cursor.fetchone()
                assert (terms["pricing_policy_id"], terms["deposit_service_days"]) == (revision, days)
                assert terms["second_payment_due_date"] == (start + timedelta(days=15) if "second" in amounts else None)
                cursor.execute("SELECT obligation_type,amount_due_ntd FROM client_obligations WHERE case_no=%s", (case_no,))
                assert {row["obligation_type"]: row["amount_due_ntd"] for row in cursor.fetchall()} == amounts
    finally:
        connection.close()


def test_subsidy_hours_change_updates_open_accounts_and_fresh_contract_preview(client):
    from infrastructure.mysql.contract_full_preview_repository import MySqlFullContractProjectionRepository
    from infrastructure.mysql.order_government_subsidy_projection_repository import MySqlOrderGovernmentSubsidyProjectionRepository
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.contract_signing.full_contract_preview import FullContractPreviewApplication
    from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow

    catalog = client.get('/api/v1/accounting-pricing').json()['data']
    post(client, '/api/v1/accounting-pricing/policies',
         {'policy': policy(), 'expected_revision': catalog['revision']}, 'subsidy-contract-policy')
    case_no = 'pricing-subsidy-contract'
    seed_case(case_no, identity='一般市民')
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE orders SET service_hours_per_day=9,service_end_time='18:00:00',"
                           "end_date='2026-10-20' WHERE case_no=%s", (case_no,))
        connection.commit()
    finally:
        connection.close()
    bootstrap_case(client, case_no)
    seed_assignment(case_no)
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT planned_hours FROM case_staff_assignments WHERE case_no=%s AND status='active'", (case_no,))
            assert cursor.fetchall() == [{'planned_hours': None}]
        with MySqlUnitOfWork(connection) as unit:
            PayrollRebuildWorkflow(MySqlPayrollRebuildRepository(connection), None).synchronize_in_unit_of_work(
                case_no, actor=ActorContext('pricing-test'), key=IdempotencyKey('subsidy-contract-salary'),
                correlation_id=CorrelationId('subsidy-contract-salary'))
            unit.commit()
    finally:
        connection.close()

    path = f'/api/v1/accounting-pricing/cases/{case_no}'
    current = client.get(path).json()['data']
    terms = {**current['terms'], 'client': {'covered': 300, 'excess': 320},
             'payroll': {'covered': 300, 'excess': 310}}
    post(client, path + '/apply', {'terms': terms, 'expected_revision': current['revision']},
         'subsidy-contract-rate-setup')

    def snapshot():
        connection = mysql_adapter.get_connection()
        try:
            preview = FullContractPreviewApplication(MySqlFullContractProjectionRepository(connection)).preview_client(case_no)
            government, = MySqlOrderGovernmentSubsidyProjectionRepository(connection).query_order_projection_facts((case_no,))
            with connection.cursor() as cursor:
                cursor.execute("SELECT obligation_type,amount_due_ntd FROM client_obligations "
                               "WHERE case_no=%s AND status<>'cancelled' AND direction='receivable_from_client' "
                               "ORDER BY obligation_identity", (case_no,))
                client_amounts = tuple(cursor.fetchall())
                cursor.execute("SELECT amount_due_ntd FROM staff_obligations WHERE case_no=%s "
                               "AND status<>'cancelled' AND obligation_kind='service_pay'", (case_no,))
                staff_amounts = tuple(row['amount_due_ntd'] for row in cursor.fetchall())
                cursor.execute('SELECT * FROM client_ledger_entries WHERE case_no=%s ORDER BY id', (case_no,))
                ledger = tuple(cursor.fetchall())
                cursor.execute('SELECT COUNT(*) AS n FROM case_pricing_events WHERE case_no=%s', (case_no,))
                events = cursor.fetchone()['n']
            return preview, client_amounts, staff_amounts, ledger, events, government.estimated_subsidy_amount_ntd
        finally:
            connection.close()

    before, before_client, before_staff, before_ledger, before_events, before_government = snapshot()
    assert before.field_values['F25'] == 180
    assert before.field_values['projected.subsidy_hours'] == 40
    assert before.field_values['projected.projected_subsidy_amount'] == 12000
    assert before_government == 12000
    assert before.field_values['B38'] == sum(row['amount_due_ntd'] for row in before_client) == 56800
    assert before.field_values['projected.staff_payable_total'] == sum(before_staff) == 55400

    current = client.get(path).json()['data']
    candidate = {**current['terms'], 'subsidy_hours': 80}
    request = {'terms': candidate, 'expected_revision': current['revision']}
    planned = post(client, path + '/preview', request, 'subsidy-contract-preview')
    assert planned['after']['covered_hours'] == 80
    assert planned['after']['client_amount'] == 56000
    assert planned['after']['staff_total_amount'] == 55000
    assert planned['after']['subsidy_amount'] == 24000
    command = {**request, 'preview_fingerprint': planned['preview_fingerprint'], 'reason': 'synthetic subsidy hours correction'}
    saved = post(client, path + '/apply', command, 'subsidy-contract-save')
    after = client.get(path).json()['data']
    assert after['revision'] == saved['revision'] == current['revision'] + 1
    assert after['terms']['subsidy_hours'] == 80
    assert after['impact'] == planned['after']

    updated, client_amounts, staff_amounts, ledger, events, government = snapshot()
    assert updated.field_values['F25'] == 180
    assert updated.field_values['projected.subsidy_hours'] == 80
    assert updated.field_values['projected.projected_subsidy_amount'] == 24000
    assert government == 24000
    assert updated.field_values['B38'] == sum(row['amount_due_ntd'] for row in client_amounts) == 56000
    assert updated.field_values['projected.staff_payable_total'] == sum(staff_amounts) == 55000
    assert updated.preview_fingerprint != before.preview_fingerprint
    assert ledger == before_ledger
    assert events == before_events + 1

    assert post(client, path + '/apply', command, 'subsidy-contract-save') == saved
    stale = client.post(path + '/apply', json=command, headers={'Idempotency-Key': 'subsidy-contract-stale'})
    assert stale.status_code == 409 and 'case_pricing_stale' in stale.text
    repeated, repeated_client, repeated_staff, repeated_ledger, repeated_events, repeated_government = snapshot()
    assert repeated.preview_fingerprint == updated.preview_fingerprint
    assert (repeated_client, repeated_staff, repeated_ledger, repeated_events, repeated_government) == (client_amounts, staff_amounts, ledger, events, government)


@pytest.mark.parametrize("cash", ["none", "partial_client", "full_client", "staff_first", "during_reprice", "client_noncash", "child_payout"])
def test_holiday_toggle_reprices_both_or_preserves_both_real_mysql(client, cash, monkeypatch):
    from infrastructure.mysql.holiday_repricing import MySqlHolidayRepricing
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.holiday_maintenance import HolidayCommand, HolidayMaintenanceApplication

    case_no = "holiday-cash-" + cash
    seed_case(case_no, identity="非市民")
    bootstrap_case(client, case_no)
    staff_id = seed_assignment(case_no)
    path = f"/api/v1/accounting-pricing/cases/{case_no}"
    current = client.get(path).json()["data"]
    terms = {**current["terms"], "client": {"covered": 0, "excess": 350},
             "payroll": {"covered": 0, "excess": 320}}
    post(client, path + "/apply", {"terms": terms, "expected_revision": current["revision"]}, case_no + ":rates")
    connection = mysql_adapter.get_connection()
    def snapshot():
        with connection.cursor() as cursor:
            cursor.execute("SELECT e.after_amount_ntd FROM client_obligations o JOIN client_obligation_events e "
                "ON e.id=o.current_event_id WHERE o.case_no=%s AND o.obligation_type IN ('deposit','first','second') "
                "ORDER BY o.obligation_identity", (case_no,))
            customer = tuple(int(row["after_amount_ntd"]) for row in cursor.fetchall())
            cursor.execute("SELECT e.after_amount_ntd FROM staff_obligations o JOIN staff_obligation_events e "
                "ON e.id=o.current_event_id WHERE o.case_no=%s AND o.obligation_kind IN ('service_pay','adjustment') "
                "AND o.status<>'cancelled' ORDER BY o.obligation_identity", (case_no,))
            staff = tuple(int(row["after_amount_ntd"]) for row in cursor.fetchall())
            cursor.execute("SELECT * FROM client_ledger_entries WHERE case_no=%s ORDER BY id", (case_no,))
            ledger = tuple(cursor.fetchall())
        return customer, staff, ledger
    try:
        with MySqlUnitOfWork(connection) as unit:
            MySqlHolidayRepricing(connection).reprice_case(case_no, case_no + ":initial", "pricing-test")
            unit.commit()
        if cash == "client_noncash":
            with connection.cursor() as cursor:
                cursor.execute("SELECT obligation_identity,amount_due_ntd FROM client_obligations "
                    "WHERE case_no=%s AND obligation_type='deposit'", (case_no,))
                obligation = cursor.fetchone()
                original = int(obligation["amount_due_ntd"])
                cursor.execute("INSERT INTO client_finance_noncash_events(case_no,target_identity,target_kind,action,"
                    "original_ntd,amount_ntd,before_remaining_ntd,after_remaining_ntd,operation_key,command_digest,"
                    "actor,reason,confirmed_on) VALUES(%s,%s,'obligation','loss',%s,1,%s,%s,%s,%s,"
                    "'pricing-test','synthetic formal noncash','2026-10-01')",
                    (case_no, obligation["obligation_identity"], original, original, original - 1, case_no, "a" * 64))
            connection.commit()
        if cash not in ("none", "during_reprice", "client_noncash"):
            with connection.cursor() as cursor:
                amount = 1 if cash in ("partial_client", "child_payout") else 56000 if cash == "full_client" else 51200
                incoming = cash not in ("staff_first", "child_payout")
                cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,credit,debit,"
                    "direction,bank_references,warnings,raw_payload,classification_type) "
                    "VALUES(%s,'sinopac','2026-10-01',%s,%s,%s,'{}','[]','{}',%s)",
                    (uuid4().hex + uuid4().hex, amount if incoming else 0, 0 if incoming else amount,
                     "incoming" if incoming else "outgoing", "client_receipt" if incoming else "staff_payout"))
                bank_id = cursor.lastrowid
                if incoming:
                    cursor.execute("INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,"
                        "occurred_on,reconciliation_reference,idempotency_key,actor,reason) "
                        "VALUES(%s,%s,'receipt',%s,'2026-10-01',%s,%s,'pricing-test','synthetic immutable receipt')",
                        (case_no, bank_id, amount, case_no, case_no))
                    ledger_id = cursor.lastrowid
                    cursor.execute("SELECT obligation_identity,amount_due_ntd FROM client_obligations "
                        "WHERE case_no=%s AND obligation_type IN ('deposit','first','second') "
                        "AND amount_due_ntd>0 ORDER BY obligation_identity", (case_no,))
                    remaining = amount
                    for ordinal, obligation in enumerate(cursor.fetchall(), start=1):
                        allocated = min(remaining, int(obligation["amount_due_ntd"]))
                        if allocated:
                            cursor.execute("INSERT INTO client_ledger_obligation_allocations "
                                "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES(%s,%s,%s,%s)",
                                (ledger_id, obligation["obligation_identity"], allocated, ordinal))
                            remaining -= allocated
                    assert remaining == 0
                else:
                    cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s "
                        "AND obligation_kind='service_pay' AND status<>'cancelled'", (case_no,))
                    identity = cursor.fetchone()["obligation_identity"]
                    if cash == "child_payout":
                        child_identity = case_no + ":child"
                        cursor.execute("INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,"
                            "obligation_kind,direction,source_obligation_identity,event_type,before_amount_ntd,after_amount_ntd,"
                            "due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) "
                            "SELECT %s,assignment_id,case_no,staff_id,'adjustment','payable_to_staff',obligation_identity,"
                            "'adjustment',0,1,due_date,%s,payroll_version,payroll_version+1,%s,'pricing-test','synthetic child' "
                            "FROM staff_obligations WHERE obligation_identity=%s", (child_identity, "a" * 64, child_identity, identity))
                        event_id = cursor.lastrowid
                        cursor.execute("INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,"
                            "obligation_kind,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,payroll_version) "
                            "SELECT %s,assignment_id,case_no,staff_id,'adjustment','payable_to_staff',obligation_identity,"
                            "1,due_date,'open',%s,payroll_version+1 FROM staff_obligations WHERE obligation_identity=%s",
                            (child_identity, event_id, identity))
                        cursor.execute("UPDATE payroll_case_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s", (case_no,))
                        identity = child_identity
                        amount = 1
                    cursor.execute("INSERT INTO staff_payout_events(staff_id,event_type,amount_ntd,occurred_on,"
                        "bank_account_identity_hash,reconciliation_reference,idempotency_key,actor,reason,finance_import_row_id) "
                        "VALUES(%s,'payout',%s,'2026-10-01',%s,%s,%s,'pricing-test','synthetic immutable payout',%s)",
                        (staff_id, amount, "a" * 64, case_no, case_no, bank_id))
                    cursor.execute("INSERT INTO staff_payout_obligation_links(payout_event_id,obligation_identity,"
                        "allocated_amount_ntd,allocation_ordinal) VALUES(%s,%s,%s,1)",
                        (cursor.lastrowid, identity, amount))
            connection.commit()
        before = snapshot()
        assert (sum(before[0]), sum(before[1])) == (56000, 51201 if cash == "child_payout" else 51200)
        repricing = MySqlHolidayRepricing(connection)
        application = HolidayMaintenanceApplication(MySqlSchedulingHolidayQuery(connection),
            lambda: MySqlUnitOfWork(connection), lambda: None, repricing, repricing.prepare)
        day = date(2026, 10, 3)
        command = HolidayCommand("upsert", day, "Synthetic holiday", True, day, day)
        preview = application.preview(command)
        if cash == "during_reprice":
            from concurrent.futures import ThreadPoolExecutor
            from threading import Event
            from infrastructure.mysql import holiday_repricing
            reached_guard = Event()
            original_guard = holiday_repricing.select_order
            def observe_guard(cursor, target_case, *, lock=False):
                if target_case == case_no and lock:
                    reached_guard.set()
                return original_guard(cursor, target_case, lock=lock)
            monkeypatch.setattr(holiday_repricing, "select_order", observe_guard)
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (case_no,))
                cursor.fetchone()
                cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
                cursor.fetchone()
            def apply_in_parallel():
                other = mysql_adapter.get_connection()
                try:
                    reprice = MySqlHolidayRepricing(other)
                    app = HolidayMaintenanceApplication(MySqlSchedulingHolidayQuery(other),
                        lambda: MySqlUnitOfWork(other), lambda: None, reprice, reprice.prepare)
                    return app.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
                        case_no + ":enable", "pricing-test", "synthetic holiday")
                finally:
                    other.close()
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(apply_in_parallel)
                assert reached_guard.wait(15), "holiday reprice did not reach fresh cash guard"
                with connection.cursor() as cursor:
                    cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,credit,"
                        "direction,bank_references,warnings,raw_payload,classification_type) "
                        "VALUES(%s,'sinopac','2026-10-01',1,'incoming','{}','[]','{}','client_receipt')",
                        (uuid4().hex + uuid4().hex,))
                    bank_id = cursor.lastrowid
                    cursor.execute("INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,"
                        "occurred_on,reconciliation_reference,idempotency_key,actor,reason) "
                        "VALUES(%s,%s,'receipt',1,'2026-10-01',%s,%s,'pricing-test','synthetic concurrent receipt')",
                        (case_no, bank_id, case_no, case_no))
                connection.commit()
                receipt = future.result(timeout=30)
            connection.rollback()
            before = snapshot()
        else:
            receipt = application.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
                case_no + ":enable", "pricing-test", "synthetic holiday")
        assert receipt.changed
        after = snapshot()
        if cash == "none":
            assert (sum(after[0]), sum(after[1])) == (58800, 53760)
            assert sum(after[0]) - sum(after[1]) == 5040
        else:
            assert after == before
        application.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
            case_no + ":enable", "pricing-test", "synthetic holiday")
        assert snapshot() == after
        off = HolidayCommand("upsert", day, "Synthetic holiday", False, day, day)
        preview_off = application.preview(off)
        application.apply(off, preview_off.calendar.holiday_version, preview_off.preview_fingerprint,
            case_no + ":disable", "pricing-test", "synthetic holiday")
        assert snapshot() == before
    finally:
        connection.close()


@pytest.mark.parametrize("cash", [False, True])
def test_holiday_merge_and_restore_use_effective_eight_hours_and_preserve_paid_total(client, cash):
    from domains.scheduling.service_date_adjustment import AdjustmentTarget
    from infrastructure.mysql.holiday_repricing import MySqlHolidayRepricing
    from infrastructure.mysql.service_date_adjustment_repository import MySqlServiceDateAdjustmentRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.service_date_adjustment import ServiceDateAdjustmentWorkflow, ServiceDateAdjustmentIntent
    case_no = "holiday-merge-" + str(cash)
    seed_case(case_no, identity="非市民")
    bootstrap_case(client, case_no)
    staff_id = seed_assignment(case_no)
    connection = mysql_adapter.get_connection()
    path = f"/api/v1/accounting-pricing/cases/{case_no}"
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE orders SET service_hours_per_day=4,service_end_time='13:00:00' WHERE case_no=%s", (case_no,))
            cursor.execute("INSERT INTO holidays(holiday_date,holiday_name,is_double_pay_default) VALUES('2026-10-25','Synthetic merge holiday',1) "
                "ON DUPLICATE KEY UPDATE is_double_pay_default=1")
        connection.commit()
        current = client.get(path).json()["data"]
        terms = {**current["terms"], "client": {"covered": 0, "excess": 350}, "payroll": {"covered": 0, "excess": 320}}
        post(client, path + "/apply", {"terms": terms, "expected_revision": current["revision"]}, case_no + ":rates")
        with MySqlUnitOfWork(connection) as unit:
            MySqlHolidayRepricing(connection).reprice_case(case_no, case_no + ":initial", "pricing-test")
            unit.commit()
        if cash:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,credit,direction,"
                    "bank_references,warnings,raw_payload,classification_type) VALUES(%s,'sinopac','2026-10-01',1,'incoming','{}','[]','{}','client_receipt')",
                    (uuid4().hex + uuid4().hex,))
                bank_id = cursor.lastrowid
                cursor.execute("INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
                    "reconciliation_reference,idempotency_key,actor,reason) VALUES(%s,%s,'receipt',1,'2026-10-01',%s,%s,'pricing-test','synthetic receipt')",
                    (case_no, bank_id, case_no, case_no))
            connection.commit()
        workflow = ServiceDateAdjustmentWorkflow(MySqlServiceDateAdjustmentRepository(connection), lambda: MySqlUnitOfWork(connection))
        intent = ServiceDateAdjustmentIntent((date(2026, 10, 1), date(2026, 10, 2)), (AdjustmentTarget(date(2026, 10, 25), staff_id),))
        preview = workflow.preview(case_no, intent)
        connection.rollback()
        receipt = workflow.apply(case_no, intent, versions=preview.facts.versions, preview_fingerprint=preview.fingerprint, key=case_no + ":merge", actor="pricing-test")
        impact = client.get(path).json()["data"]["impact"]
        assert (impact["case_total_amount"], impact["client_amount"], impact["staff_total_amount"], impact["union_income_amount"]) == ((28000, 28000, 25600, 2400) if cash else (30800, 30800, 28160, 2640))
        reverse = ServiceDateAdjustmentIntent((date(2026, 10, 25),), (), reverse_receipt_id=receipt.receipt_id)
        preview = workflow.preview(case_no, reverse)
        connection.rollback()
        workflow.apply(case_no, reverse, versions=preview.facts.versions, preview_fingerprint=preview.fingerprint, key=case_no + ":restore", actor="pricing-test")
        impact = client.get(path).json()["data"]["impact"]
        assert (impact["case_total_amount"], impact["client_amount"], impact["staff_total_amount"], impact["union_income_amount"]) == (28000, 28000, 25600, 2400)
    finally:
        connection.close()


@pytest.mark.parametrize("profile", ["citizen", "historical", "full_subsidy"])
def test_holiday_identity_scope_and_pending_funding_preserve_real_ledgers(client, profile, monkeypatch):
    from infrastructure.mysql.holiday_repricing import MySqlHolidayRepricing
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.holiday_maintenance import HolidayCommand, HolidayMaintenanceApplication
    identity = "一般市民" if profile == "citizen" else "補助市民" if profile == "full_subsidy" else "非市民"
    case_no = "holiday-scope-" + profile
    if profile == "full_subsidy":
        from subsystems.bootstrap.case_architecture_workflow import CaseArchitectureBootstrapWorkflow
        import traceback
        original_ensure = CaseArchitectureBootstrapWorkflow.ensure
        def observed_ensure(workflow, command):
            try:
                return original_ensure(workflow, command)
            except Exception:
                traceback.print_exc()
                raise
        monkeypatch.setattr(CaseArchitectureBootstrapWorkflow, "ensure", observed_ensure)
        catalog = client.get("/api/v1/accounting-pricing").json()["data"]
        configured = {**policy(), "effective_on": "2026-01-01"}
        configured["identities"] = [dict(item, subsidy_hours=160) if item["identity_name"] == "補助市民" else item
                                    for item in configured["identities"]]
        post(client, "/api/v1/accounting-pricing/policies",
             {"policy": configured, "expected_revision": catalog["revision"]}, case_no + ":policy")
    seed_case(case_no, identity=identity)
    bootstrap_case(client, case_no)
    seed_assignment(case_no)
    connection = mysql_adapter.get_connection()
    day = date(2026, 10, 19)
    def amounts():
        with connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(SUM(e.after_amount_ntd),0) AS total FROM client_obligations o "
                "JOIN client_obligation_events e ON e.id=o.current_event_id WHERE o.case_no=%s "
                "AND o.obligation_type IN ('deposit','first','second')", (case_no,))
            client_total = int(cursor.fetchone()["total"])
            cursor.execute("SELECT COALESCE(SUM(e.after_amount_ntd),0) AS total FROM staff_obligations o "
                "JOIN staff_obligation_events e ON e.id=o.current_event_id WHERE o.case_no=%s "
                "AND o.obligation_kind='service_pay' AND o.status<>'cancelled'", (case_no,))
            return client_total, int(cursor.fetchone()["total"])
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO holidays(holiday_date,holiday_name,is_double_pay_default) VALUES(%s,'Synthetic scope',0) "
                "ON DUPLICATE KEY UPDATE is_double_pay_default=0", (day,))
        connection.commit()
        with MySqlUnitOfWork(connection) as unit:
            MySqlHolidayRepricing(connection).reprice_case(case_no, case_no + ":initial", "pricing-test")
            unit.commit()
        if profile == "historical":
            with connection.cursor() as cursor:
                cursor.execute("UPDATE orders SET status='歷史訂單－服務中' WHERE case_no=%s", (case_no,))
            connection.commit()
        current = client.get(f"/api/v1/accounting-pricing/cases/{case_no}").json()["data"] if profile == "citizen" else None
        before = amounts()
        if profile == "full_subsidy":
            assert before == (0, 56000)
        reprice = MySqlHolidayRepricing(connection)
        application = HolidayMaintenanceApplication(MySqlSchedulingHolidayQuery(connection),
            lambda: MySqlUnitOfWork(connection), lambda: None, reprice, reprice.prepare)
        command = HolidayCommand("upsert", day, "Synthetic scope", True, day, day)
        preview = application.preview(command)
        receipt = application.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
            case_no + ":enable", "pricing-test", "synthetic scope")
        outcome = next(result.outcome for result in receipt.case_results if result.case_no == case_no)
        if profile == "citizen":
            after = amounts()
            assert after == (before[0] + 8 * current["terms"]["client"]["excess"],
                             before[1] + 8 * current["terms"]["payroll"]["excess"])
            assert after[0] == after[1]
            assert outcome == "repriced"
        elif profile == "full_subsidy":
            assert amounts() == (0, 58800)
            assert outcome == "repriced_funding_pending"
            result = next(item for item in receipt.case_results if item.case_no == case_no)
            assert (result.case_total_amount, result.client_receivable_amount, result.staff_payable_amount,
                    result.subsidy_amount, result.unallocated_amount) == (58800, 0, 58800, 56000, 2800)
            impact = client.get(f"/api/v1/accounting-pricing/cases/{case_no}").json()["data"]["impact"]
            assert (impact["case_total_amount"], impact["client_amount"], impact["staff_total_amount"],
                    impact["union_income_amount"]) == (58800, 0, 58800, None)
            from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
            accounting = build_accounting_workspace(connection).query(case_no)
            assert accounting.staff_receivable_ntd == 58800
            assert accounting.customer_burden_ntd == 0
            assert accounting.unallocated_service_difference_ntd == 2800
            with connection.cursor() as cursor:
                cursor.execute("SELECT funding_kind,SUM(amount_ntd) AS amount FROM staff_obligation_installments i "
                    "JOIN staff_obligations o ON o.obligation_identity=i.obligation_identity WHERE o.case_no=%s "
                    "GROUP BY funding_kind", (case_no,))
                portions = {row["funding_kind"]: int(row["amount"]) for row in cursor.fetchall()}
            assert portions.get("subsidy") == 56000
            assert portions.get("client", 0) == 0
        else:
            assert amounts() == before
            assert outcome == "historical_excluded"
        off = HolidayCommand("upsert", day, "Synthetic scope", False, day, day)
        preview = application.preview(off)
        application.apply(off, preview.calendar.holiday_version, preview.preview_fingerprint,
            case_no + ":disable", "pricing-test", "synthetic scope")
        assert amounts() == before
    finally:
        connection.close()


def _holiday_ledger_totals(connection, case_no):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COALESCE(SUM(e.after_amount_ntd),0) AS total FROM client_obligations o "
            "JOIN client_obligation_events e ON e.id=o.current_event_id WHERE o.case_no=%s "
            "AND o.obligation_type IN ('deposit','first','second')", (case_no,))
        client_total = int(cursor.fetchone()["total"])
        cursor.execute("SELECT o.staff_id,SUM(e.after_amount_ntd) AS total FROM staff_obligations o "
            "JOIN staff_obligation_events e ON e.id=o.current_event_id WHERE o.case_no=%s "
            "AND o.obligation_kind='service_pay' AND o.status<>'cancelled' GROUP BY o.staff_id", (case_no,))
        staff = {int(row["staff_id"]): int(row["total"]) for row in cursor.fetchall()}
        return client_total, staff


def _holiday_seed_ready(client, case_no):
    seed_case(case_no, identity="非市民")
    bootstrap_case(client, case_no)
    staff_id = seed_assignment(case_no)
    path = f"/api/v1/accounting-pricing/cases/{case_no}"
    current = client.get(path).json()["data"]
    terms = {**current["terms"], "client": {"covered": 0, "excess": 350},
             "payroll": {"covered": 0, "excess": 320}}
    post(client, path + "/apply", {"terms": terms, "expected_revision": current["revision"]}, case_no + ":rates")
    return staff_id


def _holiday_formal_client_receipt(connection, case_no):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,credit,direction,"
            "bank_references,warnings,raw_payload,classification_type) VALUES(%s,'sinopac','2026-10-01',1,'incoming','{}','[]','{}','client_receipt')", (uuid4().hex + uuid4().hex,))
        bank_id = cursor.lastrowid
        cursor.execute("INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
            "reconciliation_reference,idempotency_key,actor,reason) VALUES(%s,%s,'receipt',1,'2026-10-01',%s,%s,'pricing-test','synthetic receipt')",
            (case_no, bank_id, case_no, case_no))
        ledger_id = cursor.lastrowid
        cursor.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s AND obligation_type='deposit' "
            "AND amount_due_ntd>0", (case_no,))
        identity = cursor.fetchone()["obligation_identity"]
        cursor.execute("INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
            "VALUES(%s,%s,1,1)", (ledger_id, identity))
    connection.commit()


def test_holiday_batch_keeps_setting_and_distinguishes_atomic_case_failures(client, monkeypatch):
    from infrastructure.mysql import holiday_repricing
    from infrastructure.mysql.holiday_repricing import MySqlHolidayRepricing
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.holiday_maintenance import HolidayCommand, HolidayMaintenanceApplication
    cases = {kind: "holiday-batch-" + kind for kind in ("ready", "paid", "failed")}
    for case_no in cases.values():
        _holiday_seed_ready(client, case_no)
    connection = mysql_adapter.get_connection()
    day = date(2026, 10, 7)
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO holidays(holiday_date,holiday_name,is_double_pay_default) VALUES(%s,'Synthetic batch',0) "
                "ON DUPLICATE KEY UPDATE is_double_pay_default=0", (day,))
        connection.commit()
        _holiday_formal_client_receipt(connection, cases["paid"])
        before = {kind: _holiday_ledger_totals(connection, case_no) for kind, case_no in cases.items()}
        original = holiday_repricing.persist_client_finance_terms_impact
        failed_calls = []
        def fail_after_first_owner(cursor, command, **options):
            original(cursor, command, **options)
            if command.candidate.case_no == cases["failed"]:
                failed_calls.append(command.candidate.case_no)
                raise ValueError("synthetic_reprice_failure")
        monkeypatch.setattr(holiday_repricing, "persist_client_finance_terms_impact", fail_after_first_owner)
        repricing = MySqlHolidayRepricing(connection)
        app = HolidayMaintenanceApplication(MySqlSchedulingHolidayQuery(connection), lambda: MySqlUnitOfWork(connection),
            lambda: None, repricing, repricing.prepare)
        command = HolidayCommand("upsert", day, "Synthetic batch", True, day, day)
        preview = app.preview(command)
        receipt = app.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
            "holiday-batch-enable", "pricing-test", "synthetic mixed batch")
        results = {item.case_no: item for item in receipt.case_results}
        assert results[cases["ready"]].outcome == "repriced"
        assert results[cases["paid"]].outcome == "preserved_cash_history"
        assert results[cases["failed"]].outcome == "failed"
        assert results[cases["failed"]].reason_code == "synthetic_reprice_failure"
        assert _holiday_ledger_totals(connection, cases["failed"]) == before["failed"]
        assert _holiday_ledger_totals(connection, cases["paid"]) == before["paid"]
        after = _holiday_ledger_totals(connection, cases["ready"])
        assert after[0] == before["ready"][0] + 2800
        assert sum(after[1].values()) == sum(before["ready"][1].values()) + 2560
        replay = app.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
            "holiday-batch-enable", "pricing-test", "synthetic mixed batch")
        assert replay == receipt
        assert failed_calls == [cases["failed"]]
        fresh = app.preview(command)
        no_op = app.apply(command, fresh.calendar.holiday_version, fresh.preview_fingerprint,
            "holiday-batch-no-op", "pricing-test", "synthetic no-op")
        assert no_op.case_results == ()
        from infrastructure.mysql.holiday_accounting_results import query_holiday_accounting_results
        observed = query_holiday_accounting_results(connection, day, day)
        assert next(item for item in observed if item.holiday_date == day).case_results == receipt.case_results
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_double_pay_default FROM holidays WHERE holiday_date=%s", (day,))
            assert cursor.fetchone()["is_double_pay_default"] == 1
    finally:
        connection.close()


@pytest.mark.parametrize("mode", ["plain", "enabled", "ambiguous", "paid_ambiguous", "failed"])
def test_holiday_cross_assignment_merge_keeps_both_original_payees(client, mode, monkeypatch):
    from domains.scheduling.service_date_adjustment import AdjustmentTarget
    from infrastructure.mysql.holiday_repricing import MySqlHolidayRepricing
    from infrastructure.mysql.service_date_adjustment_repository import MySqlServiceDateAdjustmentRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.service_date_adjustment import ServiceDateAdjustmentWorkflow, ServiceDateAdjustmentIntent
    enabled = mode in {"enabled", "failed"}
    case_no = "holiday-cross-owner-" + mode
    first_staff = _holiday_seed_ready(client, case_no)
    connection = mysql_adapter.get_connection()
    target = date(2026, 10, 25)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT effective_generation_id FROM scheduling_aggregates WHERE case_no=%s", (case_no,))
            generation = cursor.fetchone()["effective_generation_id"]
            cursor.execute("SELECT id FROM case_staff_assignments WHERE case_no=%s", (case_no,))
            first_assignment = cursor.fetchone()["id"]
            cursor.execute("UPDATE orders SET service_days=2,service_hours_per_day=4,service_end_time='13:00:00' "
                "WHERE case_no=%s", (case_no,))
            cursor.execute("DELETE FROM staff_schedule WHERE case_no=%s AND work_date>'2026-10-02'", (case_no,))
            cursor.execute("UPDATE case_staff_assignments SET assigned_end_date='2026-10-01' WHERE id=%s", (first_assignment,))
            cursor.execute("INSERT INTO staff(name) VALUES('Synthetic second financial owner')")
            second_staff = cursor.lastrowid
            cursor.execute("INSERT INTO staff_bank_accounts(staff_id,bank_code,account_no,is_primary) VALUES(%s,'012',%s,1)",
                (second_staff, f"{second_staff:012d}"))
            cursor.execute("INSERT INTO case_staff_assignments(case_no,generation_id,staff_id,assignment_sequence,"
                "assigned_start_date,assigned_end_date,status) VALUES(%s,%s,%s,2,'2026-10-02','2026-10-02','active')",
                (case_no, generation, second_staff))
            second_assignment = cursor.lastrowid
            cursor.execute("INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,hourly_rate_ntd,"
                "source_identity_status) SELECT %s,policy_version,policy_kind,hourly_rate_ntd,source_identity_status "
                "FROM assignment_payroll_rate_snapshots WHERE assignment_id=%s", (second_assignment, first_assignment))
            cursor.execute("UPDATE staff_schedule SET assignment_id=%s,staff_id=%s WHERE case_no=%s AND work_date='2026-10-02'",
                (second_assignment, second_staff, case_no))
            cursor.execute("INSERT INTO holidays(holiday_date,holiday_name,is_double_pay_default) VALUES(%s,'Synthetic cross merge',%s) "
                "ON DUPLICATE KEY UPDATE is_double_pay_default=VALUES(is_double_pay_default)", (target, enabled))
        connection.commit()
        with MySqlUnitOfWork(connection) as unit:
            initial = MySqlHolidayRepricing(connection).reprice_case(case_no, case_no + ":initial", "pricing-test")
            assert initial.outcome in {"repriced", "unchanged"}
            unit.commit()
        assert _holiday_ledger_totals(connection, case_no) == (2800, {first_staff: 1280, second_staff: 1280})
        workflow = ServiceDateAdjustmentWorkflow(MySqlServiceDateAdjustmentRepository(connection), lambda: MySqlUnitOfWork(connection))
        intent = ServiceDateAdjustmentIntent((date(2026, 10, 1), date(2026, 10, 2)),
            (AdjustmentTarget(target, first_staff),))
        preview = workflow.preview(case_no, intent)
        connection.rollback()
        if mode == "failed":
            from infrastructure.mysql import holiday_repricing
            original = holiday_repricing.persist_client_finance_terms_impact
            def fail_after_client_write(cursor, command, **options):
                original(cursor, command, **options)
                if command.candidate.case_no == case_no:
                    raise ValueError("synthetic_date_reprice_failure")
            monkeypatch.setattr(holiday_repricing, "persist_client_finance_terms_impact", fail_after_client_write)
        receipt = workflow.apply(case_no, intent, versions=preview.facts.versions,
            preview_fingerprint=preview.fingerprint, key=case_no + ":merge", actor="pricing-test")
        expected = (5600, {first_staff: 2560, second_staff: 2560}) if enabled and mode != "failed" else (2800, {first_staff: 1280, second_staff: 1280})
        assert _holiday_ledger_totals(connection, case_no) == expected
        result = receipt.case_result
        assert result.outcome in ({"failed"} if mode == "failed" else {"repriced", "unchanged"})
        if mode == "failed":
            assert result.reason_code == "synthetic_date_reprice_failure"
            with connection.cursor() as cursor:
                cursor.execute("SELECT result_snapshot FROM service_date_adjustment_receipts WHERE id=%s", (receipt.receipt_id,))
                recorded = cursor.fetchone()["result_snapshot"]
                recorded = json.loads(recorded) if isinstance(recorded, str) else recorded
                assert recorded["case_result"]["reason_code"] == "synthetic_date_reprice_failure"
        if enabled and mode != "failed":
            assert (result.case_total_amount, result.client_receivable_amount, result.staff_payable_amount,
                    result.case_total_amount - result.staff_payable_amount) == (5600, 5600, 5120, 480)
        replay = workflow.apply(case_no, intent, versions=preview.facts.versions,
            preview_fingerprint=preview.fingerprint, key=case_no + ":merge", actor="pricing-test")
        assert replay == receipt
        assert _holiday_ledger_totals(connection, case_no) == expected
        path = f"/api/v1/accounting-pricing/cases/{case_no}"
        impact = client.get(path).json()["data"]["impact"]
        if mode != "failed":
            assert (impact["case_total_amount"], impact["staff_total_amount"], impact["union_income_amount"]) == (
                (5600, 5120, 480) if enabled else (2800, 2560, 240))
        if mode in {"ambiguous", "paid_ambiguous"}:
            from subsystems.scheduling.holiday_maintenance import HolidayCommand, HolidayMaintenanceApplication
            from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
            if mode == "paid_ambiguous":
                _holiday_formal_client_receipt(connection, case_no)
            with connection.cursor() as cursor:
                cursor.execute("UPDATE service_date_adjustment_receipts SET result_snapshot=JSON_SET(result_snapshot,"
                    "'$.removed[1].staff_id',CAST('null' AS JSON)) WHERE id=%s", (receipt.receipt_id,))
            connection.commit()
            repricing = MySqlHolidayRepricing(connection)
            app = HolidayMaintenanceApplication(MySqlSchedulingHolidayQuery(connection), lambda: MySqlUnitOfWork(connection),
                lambda: None, repricing, repricing.prepare)
            command = HolidayCommand("upsert", target, "Synthetic cross merge", True, target, target)
            preview = app.preview(command)
            applied = app.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
                case_no + ":ambiguous-enable", "pricing-test", "synthetic missing source binding")
            failure = next(item for item in applied.case_results if item.case_no == case_no)
            if mode == "paid_ambiguous":
                assert failure.outcome == "preserved_cash_history"
                assert failure.reason_code == "formal_cash_history_exists"
                assert (failure.client_receivable_amount, failure.staff_payable_amount) == (2800, 2560)
                assert failure.case_total_amount is None
                replay = app.apply(command, preview.calendar.holiday_version, preview.preview_fingerprint,
                    case_no + ":ambiguous-enable", "pricing-test", "synthetic missing source binding")
                assert replay == applied
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) AS total FROM client_ledger_entries WHERE case_no=%s", (case_no,))
                    assert cursor.fetchone()["total"] == 1
            else:
                assert failure.outcome == "failed"
                assert failure.reason_code == "holiday_service_attribution_ambiguous"
            assert "receipt_staff_binding" in failure.missing_mapping
            assert _holiday_ledger_totals(connection, case_no) == expected
    finally:
        connection.close()

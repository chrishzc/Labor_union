"""Complete HCM -> automatic charges/refund -> second-payment settlement, real MySQL."""
from datetime import date,datetime,timedelta,timezone
import os,runpy
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.mysql import mysql_adapter
from api.dependencies.hcm_import import get_hcm_workbook_import_service

DATABASE=os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicitly prepared disposable localhost database')

@pytest.fixture
def isolated(monkeypatch):
    assert DATABASE.startswith('lu_test_') and mysql_adapter.DB_CONFIG['host'] in ('localhost','127.0.0.1')
    assert os.getenv('APP_ENV')=='development'
    monkeypatch.setitem(mysql_adapter.DB_CONFIG,'database',DATABASE)
    monkeypatch.setenv('LINE_CHANNEL_ACCESS_TOKEN','');monkeypatch.setenv('REDIS_URL','')
    yield

def rows(sql,args=()):
    c=mysql_adapter.get_connection()
    try:
        with c.cursor() as q:q.execute(sql,args);return tuple(q.fetchall())
    finally:c.close()

def workbook(path,case,days):
    pd.DataFrame([{'項次':1,'案件狀態':'洽談中','查詢序號(案件編號)':case,'報名時間(建檔)':'2026/10/26 09:00:00',
      'IP位址':'127.0.0.1','姓名':'合成長案' if days>20 else '合成短案','性別':'女','行動電話':'0987654321',
      '縣市':'新竹市','地址':'新竹市東區測試路901號','身分資格':'補助市民','服務時間':'9小時 09:00-18:00',
      '預產期/預計服務開始月份':'2026/11/09','預計服務日期':'2026/11/09','希望服務天數':days,
      '居住型態':'大樓','生產方式':'自然產','服務方式':'連續服務','寶寶資訊':'單胞胎','其他事項':'隔離驗證'}]).to_excel(path,index=False)

@pytest.mark.parametrize('case,days,second',[('115000901',20,0),('115000902',30,27000)])
def test_complete_hcm_posts_all_applicable_charges_and_refund_atomically(isolated,tmp_path,case,days,second):
    path=tmp_path/(case+'.xlsx');workbook(path,case,days)
    dependency=get_hcm_workbook_import_service()
    try:
        service=next(dependency);frame=service.load_frame(str(path));plan=service.preview(frame,str(path))
        assert plan.ready_count==1 and plan.review_required_count==plan.ready_with_warning_count==0
        assert rows('SELECT case_no FROM orders WHERE case_no=%s',(case,))==()
        receipt=service.apply(frame,str(path),plan.preview_fingerprint,'six-fixes-hcm:'+case,'synthetic','six-fixes-hcm:'+case)
        assert receipt.inserted_count==1 and receipt.failed_count==0
        values={r['obligation_type']:r for r in rows('SELECT obligation_type,amount_due_ntd,due_date,direction FROM client_obligations WHERE case_no=%s',(case,))}
        assert int(values['deposit']['amount_due_ntd'])==13500
        assert int(values['first']['amount_due_ntd'])==40500
        assert int(values['subsidy_return']['amount_due_ntd'])==12000
        assert values['subsidy_return']['direction']=='payable_to_client'
        if second:
            assert int(values['second']['amount_due_ntd'])==second
            assert values['second']['due_date']==date(2026,11,24)
        else:assert 'second' not in values
        snapshot=rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))
        replay=service.apply(frame,str(path),plan.preview_fingerprint,'six-fixes-hcm:'+case,'synthetic','six-fixes-hcm:'+case)
        assert replay.replayed_workbook
        assert rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))==snapshot
        assert rows('SELECT id FROM client_ledger_entries WHERE case_no=%s',(case,))==()
        assert rows('SELECT id FROM line_delivery_tasks')==()
    finally:dependency.close()



def test_import_and_new_accounting_roll_back_together_on_failure(isolated,monkeypatch):
    from infrastructure.mysql.case_architecture_bootstrap_repository import MySqlCaseArchitectureBootstrapRepository
    from api.dependencies.case_import import build_case_import_application
    from subsystems.case_import.hcm_adapter import build_hcm_case_import_intent
    from subsystems.case_import.case_import_workflow import ApplyCaseImport,CaseImportWorkflowError
    from shared_kernel.identities import ActorContext,CorrelationId,ExpectedVersion,IdempotencyKey
    original=MySqlCaseArchitectureBootstrapRepository.synchronize_client_charges
    def fail_after_sync(self,*args):
        original(self,*args);raise RuntimeError('synthetic transaction rollback')
    monkeypatch.setattr(MySqlCaseArchitectureBootstrapRepository,'synchronize_client_charges',fail_after_sync)
    case='115000903';start=date(2026,11,9)
    intent=build_hcm_case_import_intent({'case_no':case,'name':'合成回滾','phone':'0987654321','identity_status':'補助市民',
        'service_days':30,'created_at':datetime(2026,10,26),'service_start_date':start,'service_time':'9小時 09:00-18:00',
        'service_type':'連續服務','baby_info':'單胞胎'},start+timedelta(days=29))
    c=mysql_adapter.get_connection()
    try:
        application=build_case_import_application(c);preview=application.preview(intent,CorrelationId('rollback-preview'))
        with pytest.raises(CaseImportWorkflowError):
            application.apply(ApplyCaseImport(intent,ExpectedVersion(0),preview.fingerprint,IdempotencyKey('six-fixes-rollback'),
                ActorContext('synthetic'),'',CorrelationId('rollback-apply')))
    finally:c.close()
    for table in ('clients','orders','client_finance_accounts','client_obligations','case_import_receipts','client_obligation_events'):
        assert rows(f'SELECT case_no FROM {table} WHERE case_no=%s',(case,))==()

def test_hcm_to_historical_completion_establishes_payroll_and_routes_subsidy_by_scheme(isolated, tmp_path):
    from types import SimpleNamespace
    from openpyxl import Workbook
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.historical_order_adoption import get_historical_order_workbook_import_service
    from api.routes.finance_statement_workspace import router
    from infrastructure.mysql.client_registry_query_repository import MySqlClientRegistryQueryRepository
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.client_profile.registry_query import ClientRegistryQueryApplication

    cases = ("115000961", "115000962", "115000963", "115000964")
    start, end = date(2026, 8, 1), date(2026, 8, 20)
    path = tmp_path / "hcm.xlsx"
    workbook(path, cases[0], 20)
    source = pd.read_excel(path)
    pd.concat([
        source.assign(**{"查詢序號(案件編號)": case, "身分資格": "補助市民" if i == 0 else "一般市民"})
        for i, case in enumerate(cases)
    ]).to_excel(path, index=False)
    dependency = get_hcm_workbook_import_service()
    try:
        service = next(dependency)
        frame = service.load_frame(str(path))
        preview = service.preview(frame, str(path))
        assert preview.ready_count == len(cases)
        receipt = service.apply(frame, str(path), preview.preview_fingerprint, "hcm-historical-chain", "synthetic", "hcm-historical-chain")
        assert receipt.failed_count == 0
    finally:
        dependency.close()

    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            names = tuple(f"合成月嫂-{case}" for case in cases)
            cursor.executemany("INSERT INTO staff(name,identity_card) VALUES (%s,%s)",
                               [(name, f"T{case}") for name, case in zip(names, cases)])
            # Isolated source evidence of the customer's original advance, before completion.
            cursor.execute("SELECT obligation_identity,amount_due_ntd FROM client_obligations WHERE case_no=%s "
                           "AND direction='receivable_from_client' AND amount_due_ntd>0", (cases[2],))
            original_charges = tuple(cursor.fetchall())
            assert sum(row["amount_due_ntd"] for row in original_charges) == 54000
            for charge in original_charges:
                identity, amount = charge["obligation_identity"], charge["amount_due_ntd"]
                key = f"synthetic-paid:{identity}"
                cursor.execute("INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,"
                               "reconciliation_reference,idempotency_key,actor,reason) "
                               "VALUES(%s,'receipt',%s,%s,%s,%s,'synthetic','Original paid advance fixture')",
                               (cases[2], amount, start, key, key))
                cursor.execute("INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,"
                               "amount_ntd,allocation_ordinal) VALUES(%s,%s,%s,1)",
                               (cursor.lastrowid, identity, amount))
                cursor.execute("UPDATE client_obligations SET amount_due_ntd=0,status='settled' WHERE obligation_identity=%s", (identity,))
        connection.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(1, "synthetic", "Synthetic", "system_admin")
        with TestClient(app) as http:
            for case, scheme in zip(cases, ("split", "split", "advance", "direct")):
                url = f"/cases/{case}/accounting/subsidy-plan"
                command = {"scheme": scheme, "expected_version": 0}
                response = http.post(url + "/preview", json=command)
                assert response.is_success, response.text
                command["preview_fingerprint"] = response.json()["data"]["preview_fingerprint"]
                response = http.post(url, json=command, headers={"Idempotency-Key": f"scheme:{case}"})
                assert response.is_success, response.text

            history = Workbook()
            history.active.append(["client_name", "case_no", "start_date", "end_date", "status", "staff_name"])
            for case, name in zip(cases, names):
                history.active.append(["合成短案", case, start, end, 1, name])
            path = tmp_path / "historical.xlsx"
            history.save(path)
            dependency = get_historical_order_workbook_import_service(SimpleNamespace(state=SimpleNamespace()))
            try:
                service = next(dependency)
                preview = service.preview(str(path))
                assert preview.result_counts.historical_service_completed == len(cases)
                receipt = service.apply(str(path), "hcm-historical-adoption", preview.preview_fingerprint,
                                        "synthetic", "hcm-historical-adoption")
                replay_preview = service.preview(str(path))
                replay = service.apply(str(path), "hcm-historical-reimport", replay_preview.preview_fingerprint,
                                       "synthetic", "hcm-historical-reimport")
            finally:
                dependency.close()
            assert receipt.import_counts.imported_count == len(cases)
            assert replay.import_counts.duplicate_skipped_count == len(cases)
            assert replay.payroll_issues == receipt.payroll_issues
            assert [(row.case_no, row.issue_codes) for row in receipt.payroll_issues] == [
                (cases[1], ("historical_payroll_funding_conflict",)),
            ]

            roster = ClientRegistryQueryApplication(MySqlClientRegistryQueryRepository(connection))
            for case, amount, recipient, subsidy in zip(cases, (63000, None, 54000, 54000),
                                                        ("staff", None, "client", None), (42000, None, 12000, None)):
                item, = roster.list(query=case, limit=10, after=None).items
                response = http.get(f"/cases/{case}/accounting")
                assert response.is_success, response.text
                accounting = response.json()["data"]
                if amount is None:
                    assert item.staff_payment_due_date is None
                    assert not item.staff_obligation_dates and not accounting["staff_items"]
                else:
                    assert item.staff_payment_due_date == date(2026, 9, 15)
                    assert item.staff_obligation_dates[0]["due_date"] == item.staff_payment_due_date
                    staff, = accounting["staff_items"]
                    assert staff["expected_ntd"] == amount and staff["due_date"] == "2026-09-15"
                refund_dates = [row["due_date"] for row in item.client_obligation_dates if row["obligation_type"] == "subsidy_return"]
                assert refund_dates == ([date(2026, 10, 15)] if recipient == "client" else [])
                formal = [row for row in accounting["subsidy_payments"] if row["source"] == "formal"]
                if recipient:
                    payment, = formal
                    assert (payment["recipient"], payment["amount_ntd"], payment["due_date"]) == (recipient, subsidy, "2026-10-15")
                else:
                    assert not formal
    finally:
        connection.close()

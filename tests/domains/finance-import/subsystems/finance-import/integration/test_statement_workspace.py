"""Observable archive validation, download safety and display-only warning rules."""
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_accounting_workspace, get_statement_archive_application
from api.routes.finance_statement_workspace import router
from domains.finance_import.statement_archive import accounting_warning, bank_import_type, validate_manual_statement
from subsystems.finance_import.statement_archive import StatementExportRow


@pytest.mark.parametrize('with_bank,with_marker', [(False, False), (True, False), (True, True)])
def test_case_get_projects_bank_and_historical_collections_to_strict_http_lists(with_bank, with_marker):
    from types import SimpleNamespace
    from subsystems.finance_import.accounting_workspace import (
        CaseAccounting, AccountingBankFact, HistoricalAccountingMarker, HistoricalAccountingAmount,
    )
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    case = CaseAccounting(
        '115000001', 'Synthetic', 10000, 9900, None, None, 0,
        (ClientAccountingItem('first', 'receivable', '第一期', 'Synthetic', 10000, 9900, True, '1', '2026-11-01', recognized_ntd=100),),
        (), (), (),
        bank_facts=(AccountingBankFact('bank:1', '2026-11-02', 'in', 9900, ('115000001',)),) if with_bank else (),
        historical_marker=HistoricalAccountingMarker(
            '115000001', '歷史原因無法查明', 'synthetic', '2026-11-02',
            (HistoricalAccountingAmount('first', 'receivable', 10000, 9900, 100),),
        ) if with_marker else None,
    )
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(query=lambda _: case)
    with TestClient(app) as client:
        response = client.get('/cases/115000001/accounting')
    assert response.status_code == 200
    data = response.json()['data']
    assert isinstance(data['bank_facts'], list)
    assert data['client_items'][0]['remaining_ntd'] == 0
    assert data['client_items'][0]['noncash_ntd'] == 100
    if with_bank:
        assert data['bank_facts'][0]['cases'] == ['115000001']
    if with_marker:
        assert data['historical_marker']['amounts'][0]['remaining_ntd'] == 100


@pytest.mark.parametrize("fields", [
    {"交易日": "2026-10-29", "支出": "9970", "備註": "HC115001退款"},
    {"交易日": "2026-10-29", "存入": 10000, "銷帳編號": "000001"},
    {"交易日": "2026-10-29", "支出": 10, "銷帳編號": "000001", "備註": "=1+1"},
])
def test_manual_minimum_fields_preserve_missing_values(fields):
    result = validate_manual_statement(fields)
    assert result["帳號"] is None and result["計息日"] is None
    assert result["備註"] == fields.get("備註")
    assert result["銷帳編號"] == fields.get("銷帳編號")


@pytest.mark.parametrize("update", [
    {"交易日": None}, {"交易日": "2026-02-30"}, {"支出": None},
    {"支出": "0"}, {"支出": -1}, {"支出": "NaN"}, {"支出": "1.5"},
    {"支出": True}, {"存入": "1"}, {"備註": " "}, {"未知欄位": "x"},
])
def test_invalid_manual_input_is_rejected(update):
    with pytest.raises(ValueError):
        validate_manual_statement({"交易日": "2026-10-29", "支出": "9970", "備註": "HC115001退款", **update})


@pytest.mark.parametrize("difference,warning", [(0, None), (30, None), (99, None), (100, None), (101, "under_paid"), (-1, "over_paid"), (-30, "over_paid")])
def test_payment_warning_threshold_is_display_only(difference, warning):
    assert accounting_warning("payable", 10000, 10000 - difference, True) == warning
    assert accounting_warning("payable", 10000, 0, False) is None


def test_receipt_surplus_does_not_use_payment_threshold():
    assert accounting_warning("receivable", 10000, 10001, True) == "over_received"
    assert accounting_warning("receivable", 10000, 9000, True) is None


def test_opposing_differences_never_cancel_individual_warnings():
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    class State:
        def case_client(self, _): return "Synthetic"
        def dismissed(self, _, *, for_update=False): return {}
    items = tuple(ClientAccountingItem(f"refund:{i}", "payable", "客戶退款", "Synthetic", 10000, actual, True, "1:0:0", None) for i, actual in enumerate((9850, 10150)))
    result = AccountingWorkspace(State(), lambda *_, **__: (items, ()), lambda *_, **__: ((), ())).query("case")
    assert result.payable_ntd - result.paid_ntd == 0
    assert result.pending_warning_count == 2
    assert {row.kind for row in result.warnings} == {"under_paid", "over_paid"}


@pytest.mark.parametrize('obligation_type,entry_type,direction', [('deposit','receipt','receivable_from_client'),('subsidy_return','subsidy_return','payable_to_client'),('subsidy_return','subsidy_advance','payable_to_client')])
def test_client_accounting_uses_remaining_and_effective_allocations_after_date_only_event(obligation_type,entry_type,direction):
    from infrastructure.mysql.client_payments_query_repository import query_case_accounting
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, _):
            if "FROM client_obligations o" in sql:
                self.rows = [{"obligation_identity": "deposit:case", "obligation_type": obligation_type, "direction": direction, "due_date": None, "status": "settled", "amount_due_ntd": 0, "projection_version": 2, "after_amount_ntd": 0, "account_version": 3, "client_name": "Synthetic", "confirmation_kind": None, "historical_event": None}]
            elif "FROM client_ledger_entries l" in sql:
                self.rows = [{"id": 1, "entry_type": entry_type, "occurred_on": "2026-10-29", "reversal_of_entry_id": None, "reversed_type": None, "obligation_identity": "deposit:case", "amount_ntd": 10000, "format_id": "sinopac"}]
            else:
                self.rows = []
        def fetchall(self): return self.rows
    class Connection:
        def cursor(self): return Cursor()
    items, transactions = query_case_accounting(Connection(), "case")
    assert items[0].expected_ntd == items[0].actual_ntd == 10000
    assert len(transactions) == 1


@pytest.mark.parametrize("bank,direction,result", [
    ("sinopac", "incoming", "receivable"), ("sinopac", "outgoing", "payable"),
    ("taishin", "incoming", "government_subsidy"), ("taishin", "outgoing", "subsidy_return"),
])
def test_bank_types_preserve_owner_classification_boundary(bank, direction, result):
    assert bank_import_type(bank, direction) == result


def test_full_export_keeps_both_bank_columns_and_text_without_formulas():
    class Archive:
        def export_rows(self):
            return (
                StatementExportRow("bank:1", "sinopac", "reconciled", ("115000001",), (("帳號", "000001"), ("備註", "=1+1"), ("更正註記", "Y"))),
                StatementExportRow("bank:2", "taishin", "reconciled", ("115000002",), (("台新原欄", "000002"), ("備註", "+cmd"))),
                StatementExportRow("manual:1", "manual", "manual", (), (("交易日", "2026-01-01"), ("支出", 10), ("備註", "備註"))),
            )
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_statement_archive_application] = Archive
    app.dependency_overrides[get_accounting_workspace] = lambda: object()
    with TestClient(app) as client:
        response = client.get("/statements/export")
    assert response.status_code == 200 and response.headers["X-Statement-Count"] == "3"
    workbook = load_workbook(BytesIO(response.content), data_only=False)
    assert workbook.sheetnames == ["人工新增", "永豐", "台新"]
    sheet = workbook["永豐"]
    assert sheet["A2"].value == "000001" and sheet["M2"].data_type == "s"
    assert sheet["M2"].value == "=1+1" and sheet.auto_filter.ref
    assert workbook["台新"]["A2"].value == "000002"
    assert workbook["人工新增"]["A2"].value is None


def test_export_failure_never_returns_partial_workbook_and_requires_authorization():
    class Archive:
        def export_rows(self):
            raise ValueError("sensitive raw data must not appear")
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_statement_archive_application] = Archive
    with TestClient(app) as client:
        response = client.get("/statements/export")
        assert response.status_code == 422
        assert "sensitive raw" not in response.text
        def deny():
            raise HTTPException(403, "forbidden")
        app.dependency_overrides[require_admin] = deny
        app.dependency_overrides[get_accounting_workspace] = lambda: object()
        for path in ("/statements/export", "/cases/115000001/accounting", "/accounting/warnings"):
            assert client.get(path).status_code == 403


def test_empty_export_explicitly_identifies_zero_rows_without_fabricating_facts():
    class Archive:
        def export_rows(self): return ()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_statement_archive_application] = Archive
    with TestClient(app) as client:
        response = client.get("/statements/export")
    assert response.status_code == 200 and response.headers["X-Statement-Count"] == "0"
    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["無成功明細（0筆）"]
    assert workbook.active.max_row == 1


# Monthly reporting is a query projection, never a second financial writer.
def _monthly_query():
    from datetime import date
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace, AccountingBankFact
    from subsystems.finance_import.monthly_accounting import MonthlyAccountingQuery
    class State:
        def case_client(self, case_no): return case_no
        def dismissed(self, *_args, **_kwargs): return {}
    items = {
        "S1": (ClientAccountingItem("s1", "receivable", "第一期", "client", 10000, 10000, True, "1", "2026-09-20"),),
        "S2": (ClientAccountingItem("s2", "payable", "退款", "client", 2000, 0, False, "1", None),),
        "N1": (ClientAccountingItem("n1", "receivable", "第一期", "client", 500, 500, True, "1", "2026-10-20"),),
        "H1": (ClientAccountingItem("h1", "receivable", "歷史款", "client", 777, 700, True, "1", "2026-10-20"),),
    }
    class Source:
        def recognitions(self,start,end):return ()
        def case_categories(self): return {"S1":"subsidy", "S2":"subsidy", "N1":"non_citizen", "H1":"subsidy"}
        def reporting_cases(self, start, end): return tuple(items)
        def historical_markers(self): return ("H1",)
        def bank_facts(self, start, end): return (
            AccountingBankFact("bank:1", "2026-10-10", "in", 9000, ("S1",)),
            AccountingBankFact("bank:2", "2026-10-12", "in", 1000, ("S1",)),
            AccountingBankFact("bank:3", "2026-10-15", "in", 90000, ("S1", "S2")),
            AccountingBankFact("bank:4", "2026-10-15", "in", 500, ("N1",)),
            AccountingBankFact("bank:5", "2026-10-15", "in", 700, ("H1",)),
        )
    workspace = AccountingWorkspace(State(), lambda case_no, **_: (items[case_no], ()), lambda *_, **__: ((), ()))
    return MonthlyAccountingQuery(Source(), workspace.query), date(2026, 10, 30)


def test_monthly_due_cohorts_bank_cash_and_historical_scope_are_distinct():
    query, today = _monthly_query()
    result = query.query("2026-09", "2026-10", "subsidy", today=today)
    september, october = result.rows
    assert september.expected_in_ntd == september.received_ntd == 10000
    assert september.cash_in_ntd == 0
    assert october.expected_in_ntd == 0 and october.cash_in_ntd == 100000
    assert [bank.amount_ntd for bank in october.bank_facts] == [9000, 1000, 90000]
    assert result.excluded_cases == ("H1",) and result.undated_item_count == 1
    all_cases = query.query("2026-09", "2026-10", "all", today=today)
    assert all_cases.rows[1].cash_in_ntd == 100500
    assert all_cases.rows[1].expected_in_ntd == 500


def test_recognition_uses_actual_confirmation_month_without_changing_due_or_bank_months():
    from datetime import date
    from subsystems.finance_import.monthly_accounting import AccountingRecognition
    query,_=_monthly_query()
    query.source.recognitions=lambda *_:(AccountingRecognition('loss:1',('S1',),'loss',100,'2026-11-02'),
        AccountingRecognition('historical:1',('H1',),'loss',77,'2026-11-02'))
    report=query.query('2026-09','2026-11','subsidy',today=date(2026,11,30))
    assert report.rows[0].expected_in_ntd==10000
    assert report.rows[1].cash_in_ntd==100000 and report.rows[2].cash_in_ntd==0
    assert [(e.identity,e.confirmed_on,e.amount_ntd) for e in report.recognitions]==[('loss:1','2026-11-02',100)]
    assert report.recognition_unavailable_reason is None
    query.source.recognitions=lambda *_:(AccountingRecognition('mixed:1',('S1','H1'),'loss',100,'2026-11-02'),)
    report=query.query('2026-09','2026-11','all',today=date(2026,11,30))
    assert not report.recognitions and report.recognition_unavailable_reason=='mixed_accounting_recognition_scope'


@pytest.mark.parametrize("start,end,category", [("2026-13","2026-14","all"), ("2026-11","2026-10","all"), ("2026-9","2026-10","all"), ("2026-09","2026-10","unknown")])
def test_monthly_invalid_range_does_not_query_bank_sources(start, end, category):
    query, today = _monthly_query()
    with pytest.raises(ValueError): query.query(start, end, category, today=today)


def test_monthly_does_not_invent_a_split_for_mixed_historical_bank_sources():
    from subsystems.finance_import.accounting_workspace import AccountingBankFact
    query, today = _monthly_query()
    query.source.bank_facts = lambda *_: (AccountingBankFact("bank:mixed", "2026-10-15", "out", 1000, ("S1", "H1")),)
    report = query.query("2026-09", "2026-10", "all", today=today)
    assert report.cash_unavailable_reason == 'mixed_accounting_bank_scope'
    assert report.rows[0].expected_in_ntd == 10000
    assert all(row.cash_in_ntd is None and row.cash_out_ntd is None for row in report.rows)


def test_shared_bank_scope_does_not_block_due_export_or_publish_zero_cash_totals():
    from functools import partial
    from api.dependencies.finance_import import get_monthly_accounting_query
    from subsystems.finance_import.accounting_workspace import AccountingBankFact
    query,today=_monthly_query()
    query.source.bank_facts=lambda *_:(AccountingBankFact('bank:mixed','2026-10-15','out',1000,('S1','H1')),)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_admin]=lambda:object()
    app.dependency_overrides[get_monthly_accounting_query]=lambda:type('Query',(),{'query':staticmethod(partial(query.query,today=today))})()
    with TestClient(app) as client:
        params={'start_month':'2026-09','end_month':'2026-10','category':'all'}
        response=client.get('/accounting/monthly',params=params)
        assert response.status_code==200 and response.json()['data']['rows'][0]['cash_in_ntd'] is None
        assert client.get('/accounting/monthly/export',params={**params,'basis':'due'}).status_code==200
        assert client.get('/accounting/monthly/export',params={**params,'basis':'cash'}).status_code==503


def test_receivable_items_use_due_month_and_keep_unknown_dates_out_of_monthly_money():
    from dataclasses import replace
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    query,_=_monthly_query()
    original=query.case_query
    def case_query(case_no):
        case=original(case_no)
        return replace(case,client_items=(*case.client_items,ClientAccountingItem('undated-receivable','receivable','未定日期款','client',300,0,False,'1',None))) if case_no=='S2' else case
    query.case_query=case_query
    september=query.receivables('2026-09','subsidy')
    assert [item.identity for item in september.items]==['s1'] and september.undated_count==1
    assert [item.identity for item in query.receivables('2026-10','all').items]==['n1']
    assert {item.identity for item in query.receivables(None,'all').items}=={'s1','n1'}
    unknown=query.receivables(None,'subsidy',undated_only=True)
    assert [item.identity for item in unknown.items]==['undated-receivable'] and unknown.items[0].due_date is None
    from api.dependencies.finance_import import get_monthly_accounting_query
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_admin]=lambda:object()
    app.dependency_overrides[get_monthly_accounting_query]=lambda:query
    with TestClient(app) as client:
        response=client.get('/accounting/receivables',params={'due_month':'2026-10','category':'all'})
        assert response.status_code==200 and response.json()['data']['items'][0]['identity']=='n1'
        response=client.get('/accounting/receivables',params={'category':'all','undated_only':'true'})
        assert response.status_code==200 and response.json()['data']['items'][0]['due_date'] is None
        assert client.get('/accounting/receivables',params={'due_month':'wrong'}).status_code==422


def test_historical_marker_is_version_checked_replayable_and_does_not_mutate_money():
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace, HistoricalAccountingMarker, AccountingConflict
    item = ClientAccountingItem("old", "receivable", "歷史款", "client", 10000, 9900, True, "v1", "2026-10-20")
    class State:
        marked = None
        command = None
        def case_client(self, _): return "client"
        def dismissed(self, *_args, **_kwargs): return {}
        def marker(self, _): return self.marked
        def marker_command(self, key): return self.command if key == "same-command" else None
        def begin(self): pass
        def commit(self): pass
        def rollback(self): pass
        def mark(self, case, reason, actor, versions, key, amounts):
            self.marked = HistoricalAccountingMarker(case, reason, actor, "2026-11-02", amounts)
            self.command = case, reason, actor, versions
    state = State()
    app = AccountingWorkspace(state, lambda *_args, **_: ((item,), ()), lambda *_args, **_: ((), ()))
    with pytest.raises(AccountingConflict): app.mark_historical("H1", "無法還原原因", {"old":"stale"}, "other", "actor")
    assert state.marked is None
    marker = app.mark_historical("H1", "無法還原原因", {"old":"v1"}, "same-command", "actor")
    assert app.mark_historical("H1", "無法還原原因", {"old":"v1"}, "same-command", "actor") == marker
    assert (item.expected_ntd, item.actual_ntd, item.remaining_ntd) == (10000, 9900, 100)
    assert (marker.amounts[0].expected_ntd, marker.amounts[0].actual_ntd, marker.amounts[0].remaining_ntd) == (10000, 9900, 100)
    with pytest.raises(AccountingConflict): app.mark_historical("H1", "不同原因", {"old":"v1"}, "same-command", "actor")


def test_monthly_route_and_export_share_the_same_figures():
    from api.dependencies.finance_import import get_monthly_accounting_query
    query, today = _monthly_query()
    class Application:
        def query(self, start, end, category): return query.query(start, end, category, today=today)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_monthly_accounting_query] = Application
    with TestClient(app) as client:
        response = client.get("/accounting/monthly?start_month=2026-09&end_month=2026-10&category=subsidy")
        assert response.status_code == 200
        assert response.json()["data"]["rows"][1]["cash_in_ntd"] == 100000
        download = client.get("/accounting/monthly/export?start_month=2026-09&end_month=2026-10&category=subsidy&basis=cash")
        assert download.status_code == 200
        sheet = load_workbook(BytesIO(download.content), data_only=True).active
        assert list(sheet.values)[-1] == ("合計", 100000, 0, 100000)
        assert client.get("/accounting/monthly?start_month=2026-11&end_month=2026-10").status_code == 422


@pytest.mark.parametrize('bank,direction,proof,flow', [
    ('sinopac','incoming','receipt','C'), ('taishin','incoming','government','G'),
    ('sinopac','outgoing','staff','PS'), ('taishin','outgoing','staff','PT'),
    ('sinopac','outgoing','refund','RS'), ('taishin','outgoing','subsidy_return','RT'),
])
def test_six_cash_flows_require_bank_direction_and_unique_owner_proof(bank, direction, proof, flow):
    from infrastructure.mysql.monthly_accounting_repository import _cash_flow
    row = {'format_id':bank, 'direction':direction, proof+'_proof':True}
    assert _cash_flow(row) == (bank, flow)
    assert _cash_flow({**row, proof+'_proof':False}) == (bank, None)
    other = 'refund' if proof != 'refund' else 'staff'
    assert _cash_flow({**row, other+'_proof':True}) == (bank, None)
    assert _cash_flow({**row, 'direction':'outgoing' if direction=='incoming' else 'incoming'}) == (bank, None)


@pytest.mark.parametrize('total,customer,subsidy,complete,government,expected', [
    (30000,18000,12000,False,12000,'waiting'),
    (30000,18000,12000,True,0,'split'),
    (30000,30000,12000,True,12000,'advance'),
    (30000,30000,12000,True,0,'unknown'),
    (30000,30000,0,True,0,'unknown'),
    (30000,None,12000,None,12000,'unknown'),
    (30000,20000,12000,True,12000,'unknown'),
])
def test_scheme_gate_uses_independent_terms_and_never_infers_direct_from_absent_cash(total,customer,subsidy,complete,government,expected):
    from domains.finance_import.statement_archive import case_accounting_scheme
    assert case_accounting_scheme(total,customer,subsidy,complete,government) == expected


@pytest.mark.parametrize('identity,hours,limit', [('補助市民',11,12),('補助市民',12,12),('原住民',79,80),('原住民',80,80)])
def test_full_subsidy_case_does_not_require_customer_receipts_or_three_zero_stage_records(identity,hours,limit):
    from decimal import Decimal
    from subsystems.client_finance.case_accounting_query import ClientCaseFunding, ClientCasePaymentTerms
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    class State:
        def case_client(self, _): return 'Synthetic'
        def dismissed(self, _, **kwargs): return {}
    terms = ClientCaseFunding('CASE-FULL',identity,Decimal(hours),Decimal(limit),12000)
    result = AccountingWorkspace(State(),lambda *a,**kw:((),()),lambda *a,**kw:((),()),
        subsidy=lambda _:None,payment_terms=lambda _:ClientCasePaymentTerms(terms)).query('CASE-FULL')
    assert result.scheme == 'split'
    assert result.customer_amount_ntd == 0 and result.customer_fully_received is True
    assert result.staff_receivable_ntd == result.subsidy_ntd == 12000
    assert not result.scheme_conflict


def test_full_subsidy_conflicting_existing_customer_charge_is_preserved_for_review():
    from decimal import Decimal
    from subsystems.client_finance.case_accounting_query import ClientCaseFunding, ClientCasePaymentTerms, ClientAccountingItem
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    class State:
        def case_client(self, _): return 'Synthetic'
        def dismissed(self, _, **kwargs): return {}
    item=ClientAccountingItem('original','receivable','訂金','Synthetic',500,500,True,'1',None,payment_stage='deposit')
    terms=ClientCaseFunding('CASE-FULL','原住民',Decimal(80),Decimal(80),12000)
    result=AccountingWorkspace(State(),lambda *a,**kw:((item,),()),lambda *a,**kw:((),()),
        payment_terms=lambda _:ClientCasePaymentTerms(terms)).query('CASE-FULL')
    assert result.scheme == 'unknown' and result.scheme_conflict
    assert result.client_items[0].expected_ntd == result.client_items[0].actual_ntd == 500


def test_case_cash_and_stage_progress_keep_partial_zero_stage_and_shared_source_distinct():
    from dataclasses import replace
    from domains.client_finance.reconciliation import PaymentStage
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem, ClientCasePaymentTerms
    from subsystems.staff_payables.case_accounting_query import StaffAccountingItem
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace, AccountingBankFact
    class State:
        def case_client(self, _): return 'Synthetic'
        def dismissed(self, *_, **__): return {}
        def marker(self, _): return None
    stages = tuple(ClientAccountingItem(stage,'receivable',stage,'Synthetic',amount,amount,amount>0,'v1','2026-09-20',payment_stage=stage)
                   for stage,amount in [('deposit',0),('first',18000),('second',0)])
    staff = (StaffAccountingItem('staff','payable','服務款','Synthetic',30000,30000,True,'v1','2026-09-30'),)
    banks = (AccountingBankFact('c','2026-10-01','in',18000,('CASE',),'sinopac','C'),
             AccountingBankFact('g','2026-10-02','in',12000,('CASE',),'taishin','G'),
             AccountingBankFact('p','2026-10-03','out',30000,('CASE',),'sinopac','PS'))
    from subsystems.finance_import.accounting_workspace import CaseArrangement
    State.arrangement=lambda self,case_no: CaseArrangement(case_no)
    query=AccountingWorkspace(State(),lambda *_,**__: (stages,()),lambda *_,**__: (staff,()),lambda _:banks,lambda _:12000)
    case=query.query('CASE')
    assert (case.customer_amount_ntd,case.customer_fully_received,case.scheme)==(18000,True,'split')
    assert (case.staff_receivable_ntd,case.subsidy_ntd,case.customer_burden_ntd,case.cash_net_ntd)==(30000,12000,18000,0)
    assert case.cash_by_flow=={'C':18000,'G':12000,'PS':30000,'PT':0,'RS':0,'RT':0}
    assert stages[1].due_date=='2026-09-20' and staff[0].due_date=='2026-09-30'
    # Overcollection in another stage must not silently settle the first stage.
    partial=(replace(stages[0],expected_ntd=100,actual_ntd=0),replace(stages[1],actual_ntd=18100),stages[2])
    query.client=lambda *_,**__: (partial,())
    assert query.query('CASE').scheme=='waiting'
    query.client=lambda *_,**__: (stages[1:],())
    assert query.query('CASE').customer_fully_received is None
    query.payment_terms=lambda _: ClientCasePaymentTerms(zero_stages=frozenset({PaymentStage.DEPOSIT, PaymentStage.SECOND}))
    query.client=lambda *_,**__: ((stages[1],),())
    confirmed=query.query('CASE')
    assert (confirmed.customer_amount_ntd, confirmed.customer_paid_ntd, confirmed.customer_fully_received) == (18000, 18000, True)
    assert confirmed.collection_progress.stage == 'scheme'
    assert confirmed.client_items == (stages[1],)
    query.client=lambda *_,**__: ((),())
    unknown=query.query('CASE')
    assert unknown.customer_amount_ntd is None and unknown.customer_paid_ntd is None
    assert unknown.collection_progress.stage == 'first' and not unknown.collection_progress.sources_complete
    query.client=lambda *_,**__: ((stages[1],),())
    query.bank=lambda _: (replace(banks[1],cases=('CASE','OTHER')),)
    shared=query.query('CASE')
    assert shared.cash_by_flow is None and shared.cash_net_ntd is None
    assert stages[1].actual_ntd==18000 and staff[0].actual_ntd==30000


def test_monthly_six_cash_channels_keep_original_bank_month_and_count_shared_source_once():
    from subsystems.finance_import.accounting_workspace import AccountingBankFact
    query,today=_monthly_query()
    query.source.bank_facts=lambda *_:(
        AccountingBankFact('customer','2026-10-01','in',18000,('S1',),'sinopac','C'),
        AccountingBankFact('government','2026-10-02','in',12000,('S1','S2'),'taishin','G'),
        AccountingBankFact('staff','2026-10-03','out',30000,('S1',),'sinopac','PS'),
    )
    report=query.query('2026-09','2026-10','subsidy',today=today)
    assert report.rows[0].expected_in_ntd==10000 and report.rows[0].cash_by_flow['G']==0
    october=report.rows[1]
    assert october.cash_by_flow=={'C':18000,'G':12000,'PS':30000,'PT':0,'RS':0,'RT':0}
    assert (october.cash_in_ntd,october.cash_out_ntd)==(30000,30000)
    assert len(october.bank_facts)==3
    query.source.bank_facts=lambda *_:(AccountingBankFact('unknown','2026-10-03','out',500,('S1',),'taishin',None),)
    unknown=query.query('2026-09','2026-10','subsidy',today=today).rows[1]
    assert unknown.cash_by_flow is None and unknown.cash_out_ntd==500


def _direct_arrangement_workspace():
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    from subsystems.staff_payables.case_accounting_query import StaffAccountingItem
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace, AccountingBankFact, ArrangementEvent, CaseArrangement
    class State:
        def __init__(self): self.events=[];self.commands={};self.saved=None
        def case_client(self,case):
            if case!='DIRECT':raise LookupError('accounting_case_not_found')
            return 'Synthetic'
        def dismissed(self,*_,**__): return {}
        def marker(self,_): return None
        def lock_arrangement_case(self,case): self.case_client(case)
        def arrangement(self,case): return CaseArrangement(case,len(self.events),tuple(self.events))
        def arrangement_command(self,key): return self.commands.get(key)
        def append_arrangement(self,case,version,action,reason,actor,key):
            self.events.append(ArrangementEvent(version,action,reason,actor,'2026-11-04T12:00:00+00:00'))
            self.commands[key]=(case,version-1,action,reason,actor)
        def begin(self): self.saved=(self.events[:],dict(self.commands))
        def commit(self): self.saved=None
        def rollback(self): self.events,self.commands=self.saved;self.saved=None
    stages=tuple(ClientAccountingItem(stage,'receivable',stage,'Synthetic',amount,amount,amount>0,'v1','2026-10-01',payment_stage=stage) for stage,amount in [('deposit',0),('first',30000),('second',0)])
    staff=(StaffAccountingItem('staff','payable','月嫂款','Synthetic',30000,0,False,'v1','2026-10-31'),)
    banks=(AccountingBankFact('c','2026-10-02','in',30000,('DIRECT',),'sinopac','C'),)
    state=State()
    return AccountingWorkspace(state,lambda *_,**__: (stages,()),lambda *_,**__: (staff,()),lambda _:banks,lambda _:12000),state


def test_direct_arrangement_confirmation_replay_stale_and_full_correction_history():
    from subsystems.finance_import.accounting_workspace import AccountingConflict
    query,state=_direct_arrangement_workspace()
    original=query.query('DIRECT')
    assert original.scheme=='unknown' and original.can_confirm_direct
    first=query.confirm_arrangement('DIRECT','confirm_direct',' 已確認直付 ',0,'direct-command','admin:1')
    assert first.applied_version==1 and query.query('DIRECT').scheme=='direct'
    assert query.confirm_arrangement('DIRECT','confirm_direct','已確認直付',0,'direct-command','admin:1')==first
    for reason,version,key in [('不同內容',0,'direct-command'),('已確認直付',0,'different-command')]:
        with pytest.raises(AccountingConflict):query.confirm_arrangement('DIRECT','confirm_direct',reason,version,key,'admin:1')
    query.confirm_arrangement('DIRECT','withdraw_direct','更正安排',1,'withdraw-command','admin:2')
    assert query.query('DIRECT').scheme=='unknown'
    query.confirm_arrangement('DIRECT','confirm_direct','再次確認依據',2,'reconfirm-command','admin:3')
    events=state.arrangement('DIRECT').events
    assert [(e.version,e.action,e.actor,e.reason) for e in events]==[(1,'confirm_direct','admin:1','已確認直付'),(2,'withdraw_direct','admin:2','更正安排'),(3,'confirm_direct','admin:3','再次確認依據')]
    assert all(e.created_at for e in events)
    after=query.query('DIRECT')
    assert (after.client_items,after.staff_items,after.bank_facts)==(original.client_items,original.staff_items,original.bank_facts)


@pytest.mark.parametrize('flow,direction,bank',[('G','in','taishin'),('PT','out','taishin'),('RT','out','taishin')])
def test_new_union_subsidy_cash_conflicts_with_recorded_direct_arrangement_without_erasing_it(flow,direction,bank):
    from subsystems.finance_import.accounting_workspace import AccountingBankFact, ArrangementNotReady
    query,state=_direct_arrangement_workspace()
    query.confirm_arrangement('DIRECT','confirm_direct','直付安排依據',0,'direct-command','admin:1')
    original_bank=query.bank
    query.bank=lambda case:(*original_bank(case),AccountingBankFact('later','2026-11-02',direction,12000,('DIRECT',),bank,flow))
    current=query.query('DIRECT')
    assert current.scheme=='unknown' and current.scheme_conflict and current.arrangement.direct_confirmed
    assert not current.can_confirm_direct and len(current.arrangement.events)==1
    with pytest.raises(ArrangementNotReady):query.confirm_arrangement('DIRECT','confirm_direct','衝突不能強套',1,'conflicting-command','admin:1')
    assert len(state.events)==1


def test_incomplete_or_unknown_bank_sources_cannot_be_confirmed_as_direct():
    from dataclasses import replace
    from subsystems.finance_import.accounting_workspace import ArrangementNotReady
    query,state=_direct_arrangement_workspace()
    client=query.client
    query.client=lambda *args,**kwargs:(tuple(replace(item,actual_ntd=0) if item.payment_stage=='first' else item for item in client(*args,**kwargs)[0]),())
    assert query.query('DIRECT').scheme=='waiting'
    with pytest.raises(ArrangementNotReady):query.confirm_arrangement('DIRECT','confirm_direct','尚未齊款',0,'incomplete','admin')
    query.client=client
    bank=query.bank
    query.bank=lambda case:tuple(replace(row,cases=('DIRECT','OTHER')) for row in bank(case))
    assert query.query('DIRECT').cash_by_flow is None
    with pytest.raises(ArrangementNotReady):query.confirm_arrangement('DIRECT','confirm_direct','不可把未分配當零',0,'unknown','admin')
    assert not state.events


def test_arrangement_http_contract_server_actor_strict_input_and_typed_conflicts():
    from types import SimpleNamespace
    query,state=_direct_arrangement_workspace()
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_admin]=lambda:SimpleNamespace(id=9,username='ignored-client-name')
    app.dependency_overrides[get_accounting_workspace]=lambda:query
    path='/cases/DIRECT/accounting/arrangement'
    body={'action':'confirm_direct','reason':'確認直付依據','expected_version':0}
    with TestClient(app) as client:
        assert client.get(path).json()['data']['version']==0
        response=client.post(path,json=body,headers={'Idempotency-Key':'http-command'})
        assert response.status_code==200
        assert response.json()['data']['arrangement']['events'][0]['actor']=='admin_user_id:9'
        assert client.post(path,json=body,headers={'Idempotency-Key':'http-command'}).json()['data']['applied_version']==1
        stale=client.post(path,json=body,headers={'Idempotency-Key':'new-command'})
        assert stale.status_code==409 and 'arrangement_source_changed' in stale.text
        assert client.post(path,json={**body,'actor':'spoof'},headers={'Idempotency-Key':'bad'}).status_code==422
        assert client.post(path,json={**body,'expected_version':True},headers={'Idempotency-Key':'bad'}).status_code==422
        assert client.get('/cases/OTHER/accounting/arrangement').status_code==404
        def deny():raise HTTPException(403,'forbidden')
        app.dependency_overrides[require_admin]=deny
        assert client.get(path).status_code==403 and client.post(path,json=body,headers={'Idempotency-Key':'forbidden'}).status_code==403
    assert len(state.events)==1


@pytest.mark.skipif(not __import__('os').getenv('LABOR_UNION_ARRANGEMENT_MYSQL_DATABASE'),reason='requires the explicit synthetic direct-arrangement scenario database')
def test_mysql_direct_arrangement_history_is_append_only_and_remains_contiguous():
    import os
    import pymysql
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
    database=os.environ['LABOR_UNION_ARRANGEMENT_MYSQL_DATABASE']
    assert database.startswith('lu_test_direct_arr_20261104_') and DB_CONFIG['host'] in {'localhost','127.0.0.1'}
    connection=pymysql.connect(**{**DB_CONFIG,'database':database,'cursorclass':pymysql.cursors.DictCursor,'autocommit':False})
    try:
        state=MySqlAccountingWorkspaceState(connection)
        with pytest.raises(LookupError):state.lock_arrangement_case('direct-20261104')
        connection.rollback()
        before=state.arrangement('DIRECT-20261104')
        assert before.version>=4 and [event.version for event in before.events]==list(range(1,before.version+1))
        for statement in ("UPDATE finance_case_arrangement_events SET reason='must not persist' WHERE case_no=%s AND version=1", "DELETE FROM finance_case_arrangement_events WHERE case_no=%s AND version=1"):
            with connection.cursor() as cursor:
                with pytest.raises(pymysql.MySQLError,match='immutable'):cursor.execute(statement,('DIRECT-20261104',))
            connection.rollback()
        assert state.arrangement('DIRECT-20261104')==before
    finally:
        connection.rollback();connection.close()


@pytest.mark.parametrize("values,stage,remaining,complete", [
    ((('deposit',6000,0),('first',15000,0),('second',9000,0)), 'deposit',6000,True),
    ((('deposit',6000,6000),('first',15000,14000),('second',9000,0)), 'first',1000,True),
    ((('deposit',6000,6000),('first',15000,15000),('second',9000,0)), 'second',9000,True),
    ((('deposit',6000,6000),('first',12000,12000),('second',0,0)), 'scheme',None,True),
    ((('deposit',6000,6000),('second',9000,0)), 'first',None,False),
    ((('deposit',6000,6000),('first',15000,0),('first',15000,0)), 'first',None,False),
])
def test_current_collection_item_uses_one_earliest_unfinished_stage(values,stage,remaining,complete):
    from domains.finance_import.statement_archive import CollectionStageSource, current_collection_progress
    sources=tuple(CollectionStageSource(kind,expected,received,'2026-11-05') for kind,expected,received in values)
    result=current_collection_progress(sources)
    assert (result.stage,result.remaining_ntd,result.sources_complete)==(stage,remaining,complete)
    if remaining is not None:
        assert result.due_date=='2026-11-05'
    assert tuple((source.expected_ntd,source.received_ntd) for source in sources)==tuple((value[1],value[2]) for value in values)


def test_case_query_keeps_original_stage_amounts_and_dates_for_current_item():
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    from subsystems.client_finance.case_accounting_query import ClientAccountingItem
    class State:
        def case_client(self,_):return 'Synthetic'
        def dismissed(self,_,**kwargs):return {}
    items=tuple(ClientAccountingItem(kind,'receivable',kind,'Synthetic',expected,received,received>0,'1','2026-11-05',payment_stage=kind)
                for kind,expected,received in [('deposit',6000,6000),('first',15000,14000),('second',9000,0)])
    result=AccountingWorkspace(State(),lambda *args,**kwargs:(items,()),lambda *args,**kwargs:((),())).query('Synthetic')
    assert result.collection_progress.stage=='first'
    assert result.collection_progress.remaining_ntd==1000
    assert result.collection_progress.due_date=='2026-11-05'
    assert result.client_items==items


def _plan_workspace():
    from domains.finance_import.statement_archive import CaseSubsidyPlan,SubsidyPlanEvent
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    class PlanState:
        def __init__(self): self.events=[];self.commands={};self.commits=0;self.rollbacks=0
        def begin(self): pass
        def lock_arrangement_case(self,case):
            if case!='PLAN-CASE': raise LookupError('accounting_case_not_found')
        def case_client(self,case): self.lock_arrangement_case(case);return 'Synthetic'
        def subsidy_plan(self,case): return CaseSubsidyPlan(case,len(self.events),tuple(self.events))
        def subsidy_plan_command(self,key): return self.commands.get(key)
        def append_subsidy_plan(self,case,version,scheme,actor,key):
            self.commands[key]=(case,version-1,scheme,actor)
            self.events.append(SubsidyPlanEvent(version,scheme,actor,'2026-11-05T00:00:00+00:00'))
        def commit(self): self.commits+=1
        def rollback(self): self.rollbacks+=1
    def no_finance(*args,**kwargs): raise AssertionError('plan setting must not require or mutate financial facts')
    state=PlanState()
    return state,AccountingWorkspace(state,no_finance,no_finance)


@pytest.mark.parametrize('scheme',['split','advance','direct'])
def test_human_plan_can_be_saved_before_collection_without_financial_calls(scheme):
    state,workspace=_plan_workspace()
    result=workspace.save_subsidy_plan('PLAN-CASE',scheme,0,'operation-1','admin:1')
    assert result.applied_version==1 and result.plan.selected_scheme==scheme
    assert state.commits==1 and state.events[0].actor=='admin:1'


def test_manual_plan_replays_original_operation_after_later_change_and_rejects_changed_key():
    from subsystems.finance_import.accounting_workspace import AccountingConflict
    state,workspace=_plan_workspace()
    workspace.save_subsidy_plan('PLAN-CASE','split',0,'operation-1','admin:1')
    workspace.save_subsidy_plan('PLAN-CASE','direct',1,'operation-2','admin:2')
    replay=workspace.save_subsidy_plan('PLAN-CASE','split',0,'operation-1','admin:1')
    assert replay.applied_version==1 and replay.plan.version==2 and len(state.events)==2
    with pytest.raises(AccountingConflict,match='command_changed'):
        workspace.save_subsidy_plan('PLAN-CASE','advance',0,'operation-1','admin:1')
    with pytest.raises(AccountingConflict,match='version_changed'):
        workspace.save_subsidy_plan('PLAN-CASE','advance',0,'operation-new','admin:1')
    assert len(state.events)==2 and state.rollbacks==2


@pytest.mark.parametrize('received,selected,completed',[(False,'split',False),(None,'direct',False),(True,None,False),(True,'advance',True),(True,'direct',True)])
def test_ongoing_completion_requires_collection_and_explicit_human_plan(received,selected,completed):
    from domains.finance_import.statement_archive import CaseSubsidyPlan,SubsidyPlanEvent,ongoing_case_completed
    plan=CaseSubsidyPlan('PLAN-CASE',1,(SubsidyPlanEvent(1,selected,'admin','2026-11-05T00:00:00+00:00'),)) if selected else CaseSubsidyPlan('PLAN-CASE')
    assert ongoing_case_completed(received,plan) is completed


def test_manual_plan_body_does_not_accept_forged_actor_or_financial_values():
    from pydantic import ValidationError
    from api.schemas.finance_import import SubsidyPlanBody
    with pytest.raises(ValidationError): SubsidyPlanBody(scheme='direct',expected_version=0,actor='forged')
    with pytest.raises(ValidationError): SubsidyPlanBody(scheme='direct',expected_version=0,amount_ntd=10)

def test_case_manual_supplement_api_endpoint_success(monkeypatch):
    """Transport only: this test must never execute project SQL."""
    from types import SimpleNamespace
    import api.routes.finance_statement_workspace as routes
    from subsystems.finance_import.accounting_workspace import CaseAccounting

    case = CaseAccounting('115000001', 'Synthetic', 1000, 300, None, None, 0, (), (), (), ())
    calls = []

    class Connection:
        def begin(self): calls.append("begin")
        def cursor(self): raise AssertionError("project SQL is forbidden in this transport test")
        def commit(self): calls.append("commit")
        def rollback(self): calls.append("rollback")

    connection = Connection()

    class Service:
        def __init__(self, actual): assert actual is connection
        def execute(self, **command): calls.append(command)

    monkeypatch.setattr("subsystems.finance_import.case_manual_supplement.CaseManualSupplementService", Service)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(
        query=lambda _: case, state=SimpleNamespace(connection=connection),
    )
    with TestClient(app) as client:
        response = client.post(
            "/cases/115000001/manual-supplement", headers={"Idempotency-Key": "manual-test-key"},
            json={"bank": "sinopac", "direction": "client_receipt", "target_item": "deposit:case",
                  "amount_ntd": 300, "transaction_date": "2026-11-06"},
        )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls[0] == "begin"
    assert calls[1]["case_no"] == "115000001"
    assert calls[1]["target_item"] == "deposit:case" and calls[1]["amount_ntd"] == 300
    assert calls[1]["actor"] == "admin_user_id:1"
    assert calls[2:] == ["commit"]


@pytest.mark.parametrize("failure,expected_status,expected_code", [
    ("idempotency", 409, "accounting_source_changed"),
    ("target", 409, "accounting_source_changed"),
    ("overage", 422, "client_receipt_overpaid"),
    ("unavailable", 503, "accounting_unavailable"),
])
def test_case_manual_supplement_api_rejection_rolls_back_without_success(monkeypatch, failure, expected_status, expected_code):
    """Exercise the real route/error adapter with a SQL-free service port."""
    from types import SimpleNamespace
    import api.routes.finance_statement_workspace as routes
    from infrastructure.mysql.client_receipt_reconciliation_repository import ClientReceiptRepositoryUnavailable
    from shared_kernel.errors import ErrorCategory, TypedError
    from shared_kernel.identities import CorrelationId
    from subsystems.client_finance.reconciliation_workflow import ClientReconciliationError
    from subsystems.finance_import.accounting_workspace import AccountingConflict
    from subsystems.finance_import.statement_archive import StatementCommandConflict

    calls = []

    class Connection:
        def begin(self): calls.append("begin")
        def cursor(self): raise AssertionError("project SQL is forbidden in this transport test")
        def commit(self): calls.append("commit")
        def rollback(self): calls.append("rollback")

    class Service:
        def __init__(self, connection): pass
        def execute(self, **command):
            if failure == "idempotency": raise StatementCommandConflict("idempotency_conflict")
            if failure == "target": raise AccountingConflict("manual_supplement_target_not_current")
            if failure == "unavailable": raise ClientReceiptRepositoryUnavailable("synthetic")
            raise ClientReconciliationError(TypedError(
                ErrorCategory.DOMAIN_BLOCKED, "client_receipt_overpaid", "Review required.",
                CorrelationId("manual-test"), domain_blockers=("client_receipt_overpaid",),
            ))

    def query(_): raise AssertionError("a rejected command must not return a successful case view")
    monkeypatch.setattr("subsystems.finance_import.case_manual_supplement.CaseManualSupplementService", Service)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(
        query=query, state=SimpleNamespace(connection=Connection()),
    )
    with TestClient(app) as client:
        response = client.post(
            "/cases/115000001/manual-supplement", headers={"Idempotency-Key": "manual-test-key"},
            json={"bank": "sinopac", "direction": "client_receipt", "target_item": "deposit:case",
                  "amount_ntd": 300, "transaction_date": "2026-11-06"},
        )
    assert response.status_code == expected_status
    assert response.json()["detail"]["error"]["code"] == expected_code
    assert calls == ["begin", "rollback"]

@pytest.mark.parametrize("operation", ["manual", "exclude"])
@pytest.mark.parametrize("fail", [False, True])
def test_statement_archive_application_owns_command_transaction(operation, fail):
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.finance_import.statement_archive import (
        StatementArchiveApplication, StatementCommandConflict, StatementCommandReceipt,
    )
    events = []
    receipt = StatementCommandReceipt("manual:7", 1, 0)
    failure = StatementCommandConflict("idempotency_conflict")

    class Connection:
        # The real transaction guard runs; no SQL cursor can be created.
        def begin(self): events.append("begin")
        def commit(self): events.append("commit")
        def rollback(self): events.append("rollback")

    class Repository:
        def export_rows(self): events.append("query"); return ()
        def create_manual(self, fields, key, actor, duplicate_of):
            assert fields["支出"] == 300
            assert (key, actor, duplicate_of) == ("key", "actor", None)
            return self.write()
        def exclude_duplicate(self, candidate, kept, key, actor):
            assert (candidate, kept, key, actor) == ("bank:8", "manual:7", "key", "actor")
            return self.write()
        def write(self):
            events.append("write")
            if fail: raise failure
            return receipt

    application = StatementArchiveApplication(Repository(), lambda: MySqlUnitOfWork(Connection()))
    assert application.export_rows() == ()
    assert events == ["query"]
    events.clear()

    def command():
        if operation == "manual":
            return application.create_manual({"交易日": "2026-11-06", "支出": 300, "備註": "synthetic"}, "key", "actor")
        return application.exclude_duplicate("bank:8", "manual:7", "key", "actor")

    if fail:
        with pytest.raises(StatementCommandConflict) as caught:
            command()
        assert caught.value is failure
    else:
        assert command() is receipt
    assert events == ["begin", "write", "rollback" if fail else "commit"]

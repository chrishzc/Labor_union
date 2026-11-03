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

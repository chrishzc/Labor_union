"""Customer subsidy case visibility and amount/date owner acceptance."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_subsidy_return_query import get_subsidy_return_query_repository
from api.routes.finance_reports import router
from subsystems.client_finance.subsidy_return_query import SubsidyReturnCaseFacts, query_subsidy_returns


def case(case_no='CASE-A', **changes):
    return replace(SubsidyReturnCaseFacts(case_no, '測試客戶', '訂單完成', '一般市民',
        Decimal('180'), Decimal('0'), 300, date(2026, 11, 30), False, None, None, False), **changes)


class Repository:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def query_facts(self, **options):
        self.calls.append(options)
        return self.facts


def test_eligible_case_without_posted_refund_is_visible_using_frozen_terms():
    result = query_subsidy_returns(Repository((case(), case('CASE-B', client_hourly_rate_ntd=450))))
    assert [(row.case_no, row.amount_ntd, row.due_date, row.is_estimate) for row in result.rows] == [
        ('CASE-A', 12000, date(2027, 1, 15), True), ('CASE-B', 18000, date(2027, 1, 15), True)]


def test_excludes_cancelled_full_subsidy_no_entitlement_and_completed_refund():
    facts = (
        case('CANCEL', order_status='訂單取消', has_formal_return=True, formal_amount_ntd=12000),
        case('FULL', identity_status='低收入戶', service_hours=Decimal('120')),
        case('NO-ENTITLEMENT', identity_status='非市民'),
        case('PAID', return_settled=True),
        case('EXCESS', identity_status='補助市民', client_hourly_rate_ntd=350),
        case('FLOOR', identity_status='中低收入戶', service_hours=Decimal('120'), floor_fee=Decimal('600'), client_hourly_rate_ntd=350),
    )
    result = query_subsidy_returns(Repository(facts))
    assert [(row.case_no, row.amount_ntd) for row in result.rows] == [('EXCESS', 42000), ('FLOOR', 42000)]


def test_formal_refund_overrides_estimate_without_recipient_bank_requirements():
    fact = case(has_formal_return=True, formal_amount_ntd=9000, formal_due_date=date(2026, 9, 15))
    row, = query_subsidy_returns(Repository((fact,))).rows
    assert (row.amount_ntd, row.due_date, row.is_estimate) == (9000, date(2026, 9, 15), False)


def test_unknown_amount_and_date_are_not_zero_or_planned_completion():
    facts = (case('MISSING', service_hours=None, client_hourly_rate_ntd=None),
             case('ONGOING', order_status='服務中'))
    result = query_subsidy_returns(Repository(facts))
    assert result.rows[0].amount_ntd is None
    assert result.rows[1].due_date is None
    assert result.rows[1].amount_ntd == 12000


def test_month_filter_and_cursor_use_scanned_cases_even_when_excluded():
    repository = Repository((case('A', identity_status='非市民'), case('B'), case('C')))
    result = query_subsidy_returns(repository, page_size=2, search='測試', after_case_no='0', target_month='2026-12')
    assert not result.rows
    assert result.next_cursor == 'B'
    assert repository.calls == [dict(after_case_no='0', case_no=None, search='測試', limit=3)]
    assert len(query_subsidy_returns(Repository((case(),)), target_month='2027-01').rows) == 1


def test_get_contract_is_bounded_and_does_not_expose_private_facts():
    app = FastAPI()
    app.include_router(router)
    repository = Repository((case(),))
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_subsidy_return_query_repository] = lambda: repository
    client = TestClient(app)
    result = client.get('/api/v1/finance-reports/client-subsidy-returns?case_no=CASE-A').json()
    assert result['success'] is True
    assert result['data']['rows'][0] == dict(case_no='CASE-A', client_name='測試客戶', order_status='訂單完成',
        amount_ntd=12000, due_date='2027-01-15', is_estimate=True)
    assert repository.calls[0]['case_no'] == 'CASE-A'
    assert client.get('/api/v1/finance-reports/client-subsidy-returns?page_size=201').status_code == 422
    assert client.get('/api/v1/finance-reports/client-subsidy-returns?target_month=2026-13').status_code == 422

    def forbidden():
        raise HTTPException(403, 'forbidden')
    app.dependency_overrides[require_admin] = forbidden
    assert client.get('/api/v1/finance-reports/client-subsidy-returns').status_code == 403

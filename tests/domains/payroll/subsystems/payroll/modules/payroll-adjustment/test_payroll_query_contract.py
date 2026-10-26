"""Payroll API read responses retain legitimate zero-valued terminal obligations."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.payroll import get_payroll_application
from api.routes.payroll import router
from api.schemas.payroll import PayrollObligationView
from subsystems.access.authentication_session import AdminPrincipal


def obligation(amount,status,identity='synthetic-terminal'):
    return dict(obligation_identity=identity,assignment_id=1,case_no='SYNTHETIC-PAYROLL-READ',
        staff_id=1,obligation_kind='service_pay',direction='payable_to_staff',
        source_obligation_identity=None,amount_due_ntd=amount,due_date=None,
        status=status,payout_history_exists=False)


@pytest.mark.parametrize('status',['cancelled','settled'])
@pytest.mark.parametrize('scope',['case','staff'])
def test_read_endpoints_return_terminal_zero_and_positive_open_amounts(scope,status):
    app=FastAPI();app.include_router(router)
    obligations=[obligation(0,status),obligation(12000,'open','synthetic-open')]
    calls=[]
    def query_case(case):
        calls.append(('case',case))
        return dict(case_no=case,payroll_version=1,staff_payment_due_date=None,
                    obligations=obligations,adjustments=[])
    def query_staff(staff):
        calls.append(('staff',staff))
        return dict(staff_id=staff,obligations=obligations)
    app.dependency_overrides[get_payroll_application]=lambda:SimpleNamespace(
        query_case=query_case,query_staff=query_staff)
    app.dependency_overrides[require_system_admin]=lambda:AdminPrincipal(1,'synthetic','Synthetic','system_admin')
    path='/api/v1/payroll/cases/SYNTHETIC-PAYROLL-READ' if scope=='case' else '/api/v1/payroll/staff/1/obligations'
    with TestClient(app) as http:response=http.get(path)
    assert response.status_code==200
    rows=response.json()['data']['obligations']
    assert [(row['amount_due_ntd'],row['status']) for row in rows]==[(0,status),(12000,'open')]
    assert len(calls)==1 and calls[0][0]==scope


def test_payroll_read_response_still_rejects_negative_amounts():
    with pytest.raises(ValidationError):PayrollObligationView.model_validate(obligation(-1,'cancelled'))

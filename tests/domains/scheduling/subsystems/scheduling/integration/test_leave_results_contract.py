"""Leave transport authority, retirement and typed input contracts; no DB/provider."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from domains.scheduling.leave_result import LeaveDateChange, LeaveResultSubmission


@pytest.mark.parametrize('decision,dates',[
    ('defer',()),
    ('defer',(LeaveDateChange(date(2027,1,5)),)),
    ('defer',(LeaveDateChange(date(2027,1,5),date(2027,1,5)),)),
    ('defer',(LeaveDateChange(date(2027,1,5),date(2027,2,5)),LeaveDateChange(date(2027,1,5),date(2027,2,6)))),
    ('substitute',(LeaveDateChange(date(2027,1,5),date(2027,2,5)),)),
])
def test_invalid_outcomes_are_not_commands(decision,dates):
    with pytest.raises(ValueError):LeaveResultSubmission('CASE',1,1,decision,dates,1,1,'key')


def test_staff_subject_is_server_owned_and_old_pending_intake_is_closed(monkeypatch):
    from api.routes import staff_leave_intake as route
    from api.dependencies.service_start import get_service_start_application
    from api.dependencies.staff_leave_intake import get_staff_leave_intake_application
    app=FastAPI();app.include_router(route.router)
    service=Mock()
    app.dependency_overrides[get_service_start_application]=lambda:service
    app.dependency_overrides[get_staff_leave_intake_application]=lambda:object()
    monkeypatch.setattr(route,'_verified_staff_context',lambda body:(object(),{'staff_id':8}))
    service.leave_cases.return_value=()
    with TestClient(app) as http:
        assert http.post('/api/v1/line/staff-self-service/leave-results/cases',json={'line_id_token':'synthetic'}).status_code==200
        service.leave_cases.assert_called_once_with(8)
        for path in ['/leave-requests','/leave-requests/preview']:
            result=http.post('/api/v1/line/staff-self-service'+path,json={'line_id_token':'synthetic','leave_start_date':'2027-01-05','leave_end_date':'2027-01-06','leave_reason':''},headers={'Idempotency-Key':'test'})
            assert result.status_code==410
        payload={'line_id_token':'synthetic','case_no':'CASE','assignment_id':1,'decision':'substitute',
            'dates':[{'original_date':'2027-01-05'}],'expected_order_version':1,'expected_scheduling_version':1,'idempotency_key':'test','staff_id':999}
        assert http.post('/api/v1/line/staff-self-service/leave-results/submit',json=payload).status_code==422
        service.submit_leave.assert_not_called()


def test_old_customer_card_postbacks_create_no_decisions_or_acknowledgement():
    from subsystems.line.staff_leave_customer_coordination import StaffLeaveCustomerCoordinationApplication
    application=StaffLeaveCustomerCoordinationApplication(Mock(),Mock(),Mock())
    unit=Mock()
    inbox=SimpleNamespace(event=SimpleNamespace(payload_json=json.dumps({'postback':{'data':'leave_customer_decision:request_id=1&version=1&case_no=CASE&decision=agree_defer'}})))
    assert application.handle_postback(inbox,unit)
    assert unit.mock_calls==[]


def test_queued_old_customer_confirmations_never_call_provider():
    from subsystems.line.delivery_worker import LineDeliveryWorker
    worker=LineDeliveryWorker.__new__(LineDeliveryWorker)
    for source in ['staff_leave_customer_coordination','staff_leave_customer_decision']:
        task=SimpleNamespace(request=SimpleNamespace(source_aggregate_type=source))
        assert worker._manual_replay_validation_failure(task)=='leave_customer_confirmation_retired'


def test_substitute_inquiry_lists_only_the_selected_nonconsecutive_dates():
    from subsystems.line.service_start_messages import substitute_inquiry
    card=substitute_inquiry('CASE',date(2027,1,5),date(2027,1,10),'synthetic',
                            service_dates=['2027-01-05','2027-01-10'])
    text=card['contents']['body']['contents'][1]['text']
    assert '服務日期：2027-01-05、2027-01-10' in text
    assert '～' not in text

from dataclasses import asdict
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.line_payment_overdue_reminders import router
from api.routes import line_payment_receipt_notifications as route
from api.dependencies.admin_auth import require_admin
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.payment_receipt_notifications import PaymentReceiptSnapshot,PaymentReceiptTodo,PaymentReceiptConflict
from subsystems.line.notification_policy import evaluate_notification_rules,NotificationSourceEvent

PAYMENT=PaymentReceiptSnapshot('DEMO-001','deposit','a'*64,12000,2,'source')
@pytest.fixture
def http():
    calls=[];state={'stale':False}
    def send(expected,actor):
        if state['stale']:raise PaymentReceiptConflict('payment_receipt_changed')
        calls.append(expected);return 1,'pending'
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_admin]=lambda:AdminPrincipal(1,'synthetic','人員','system_admin')
    app.dependency_overrides[route.application]=lambda:SimpleNamespace(list=lambda *_:((PaymentReceiptTodo(PAYMENT,True,None,None),),1),send=send)
    with TestClient(app) as client:yield client,calls,state,app

def test_query_never_sends_and_explicit_post_uses_closed_snapshot(http):
    client,calls,_,_=http
    assert client.get('/api/v1/line/payment-overdue-reminders/receipts').status_code==200 and calls==[]
    assert client.post('/api/v1/line/payment-overdue-reminders/receipts/send',json=asdict(PAYMENT)).status_code==200
    assert calls==[PAYMENT]
    assert client.post('/api/v1/line/payment-overdue-reminders/receipts/send',json={**asdict(PAYMENT),'recipient':'group'}).status_code==422

def test_stale_is_typed_conflict_and_read_only_principal_cannot_send(http):
    client,calls,state,app=http;state['stale']=True
    assert client.post('/api/v1/line/payment-overdue-reminders/receipts/send',json=asdict(PAYMENT)).status_code==409 and calls==[]
    app.dependency_overrides[require_admin]=lambda:AdminPrincipal(2,'reader','唯讀','read_only')
    assert client.post('/api/v1/line/payment-overdue-reminders/receipts/send',json=asdict(PAYMENT)).status_code==403

@pytest.mark.parametrize('event',['deposit_confirmed','client.second_payment_settled'])
def test_enabled_old_rules_still_cannot_authorize_an_automatic_receipt(event):
    decisions=evaluate_notification_rules(NotificationSourceEvent('synthetic',event,False,{}),{'rules':[{'id':'old','event_code':event,'enabled':True,'predicates':[]}]})
    assert decisions[0].status=='suppressed' and decisions[0].reason_code=='payment_receipt_requires_human_send'

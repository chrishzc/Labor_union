"""
File: test_payment_receipt_api.py
Description: 驗證入帳待辦查詢、已於官方帳號發送標記消除、停用自動與手動推播行為。
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.line_payment_overdue_reminders import router
from api.routes import line_payment_receipt_notifications as route
from api.dependencies.admin_auth import require_admin
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineDeliveryTaskId, LineUserId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.capabilities import LineCapability
from subsystems.line.payment_receipt_notifications import (
    MANUAL_RECEIPT,
    PaymentReceiptCandidate,
    PaymentReceiptConflict,
    PaymentReceiptHistory,
    PaymentReceiptNotificationApplication,
    PaymentReceiptSnapshot,
    PaymentReceiptTodo,
    payment_receipt_delivery_is_current,
    receipt_ack_key,
)
from subsystems.line.notification_policy import evaluate_notification_rules,NotificationSourceEvent

PAYMENT=PaymentReceiptSnapshot('DEMO-001','deposit','a'*64,12000,2,'source')
@pytest.fixture
def http():
    calls=[];state={'stale':False}
    def send(expected,actor):
        if state['stale']:raise PaymentReceiptConflict('payment_receipt_changed')
        calls.append(expected);return 1,'completed'
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


def test_first_receipt_focus_is_passed_to_owner_and_get_does_not_send(http):
    client,calls,_,app=http;queries=[]
    app.dependency_overrides[route.application]=lambda:SimpleNamespace(list=lambda *args,**kwargs:(queries.append(kwargs) or ((),0)),send=lambda *_:pytest.fail('GET cannot send'))
    result=client.get('/api/v1/line/payment-overdue-reminders/receipts',params={'case_no':'DEMO-001','payment_stage':'first','settlement_identity':'a'*64})
    assert result.status_code==200 and calls==[]
    assert queries==[{'case_no':'DEMO-001','payment_stage':'first','settlement_identity':'a'*64}]

@pytest.mark.parametrize('event',['deposit_confirmed','client.second_payment_settled'])
def test_enabled_old_rules_still_cannot_authorize_an_automatic_receipt(event):
    decisions=evaluate_notification_rules(NotificationSourceEvent('synthetic',event,False,{}),{'rules':[{'id':'old','event_code':event,'enabled':True,'predicates':[]}]})
    assert decisions[0].status=='suppressed' and decisions[0].reason_code=='payment_receipt_requires_human_send'


def test_application_send_dismisses_todo_via_receipt_without_enqueueing_push():
    receipts = {}
    audits = []
    committed = []
    payment_row = SimpleNamespace(
        case_no='DEMO-001',
        settlement_identity='a' * 64,
        amount_ntd=12000,
        obligation_version=2,
        obligation_identity='dep-1',
        due_date='2026-11-01',
        virtual_account='99781699116001',
    )

    class Repo:
        def candidates(self, after, limit):
            return () if after else (PaymentReceiptCandidate(1, 'DEMO-001', 'deposit', 'a' * 64),)

        def payment(self, case_no, stage, identity, *, lock=False):
            return payment_row if (case_no, stage, identity) == ('DEMO-001', 'deposit', 'a' * 64) else None

        def history(self, snapshot, *, lock=False):
            key = receipt_ack_key(snapshot).value
            return PaymentReceiptHistory('acknowledged', 0) if key in receipts else None

    class Unit:
        payment_receipt_notifications = Repo()
        delivery_tasks = SimpleNamespace(enqueue=lambda *_: pytest.fail('must not enqueue push delivery task'))
        receipts = SimpleNamespace(
            get=lambda key, for_update=False: receipts.get(key.value),
            append=lambda rec: receipts.__setitem__(rec.key.value, rec),
        )
        audit = SimpleNamespace(append=lambda intent: audits.append(intent))

        def commit(self):
            committed.append(True)

    @contextmanager
    def units():
        yield Unit()

    now = datetime(2026, 11, 14, 0, tzinfo=timezone.utc)
    app = PaymentReceiptNotificationApplication(units, lambda: now)
    todos, total = app.list()
    assert total == 1 and len(todos) == 1 and todos[0].can_send is True and todos[0].unavailable_reason is None
    actor = ActorContext('admin:1', (LineCapability.TASK_SEND.value,))
    with pytest.raises(PaymentReceiptConflict, match='payment_receipt_changed'):
        app.send(PaymentReceiptSnapshot('DEMO-001', 'deposit', 'a' * 64, 9999, 2, todos[0].payment.source_reference), actor)
    assert app.send(todos[0].payment, actor) == (1, 'completed')
    assert app.send(todos[0].payment, actor) == (1, 'completed')
    assert len(audits) == 1 and audits[0].action == 'payment_receipt_acknowledged'
    assert len(committed) == 1
    assert app.list() == ((), 0)


def test_payment_receipt_worker_guard_cancels_residual_manual_and_auto_tasks():
    cancelled = []
    committed = []

    class Unit:
        payment_receipt_notifications = SimpleNamespace(automatic_receipt=lambda t: t.request.source_aggregate_type == 'client_finance_account')
        delivery_tasks = SimpleNamespace(cancel=lambda cmd: cancelled.append(cmd))

        def commit(self):
            committed.append(True)

    for idx, source in enumerate((MANUAL_RECEIPT, 'client_finance_account'), start=1):
        task = SimpleNamespace(
            task_id=LineDeliveryTaskId(idx),
            request=LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, LineUserId('U-test')),
                LineMessageKind.TEXT,
                '{}',
                datetime(2026, 11, 14, 0, tzinfo=timezone.utc),
                IdempotencyKey(f'k-{idx}'),
                CorrelationId(f'DEMO-001:{idx}'),
                source,
                'deposit:' + ('a' * 64),
            ),
        )
        assert payment_receipt_delivery_is_current(Unit(), task, datetime(2026, 11, 14, 0, tzinfo=timezone.utc)) is False
    assert [cmd.task_id.value for cmd in cancelled] == [1, 2]
    assert len(committed) == 2

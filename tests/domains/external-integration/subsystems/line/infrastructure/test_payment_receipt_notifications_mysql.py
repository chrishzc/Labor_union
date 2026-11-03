"""Native isolated DB oracle: reads/worker scans never send; only human commands do."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
from datetime import date
import json,runpy,pytest
from shared_kernel.identities import ActorContext,IdempotencyKey,ExpectedVersion,CorrelationId
from infrastructure.mysql import mysql_adapter
from subsystems.line.capabilities import LineCapability,LineCapabilityDeniedError
from subsystems.line.deposit_notifications import DepositNotificationApplication,SETTLED,settlement_key
from subsystems.line.payment_receipt_notifications import PaymentReceiptNotificationApplication,PaymentReceiptConflict,MANUAL_RECEIPT,receipt_snapshot

support=runpy.run_path('tests/domains/external-integration/subsystems/line/infrastructure/test_payment_reminder_notifications_mysql.py')
pytestmark=support['pytestmark'];isolated_database=support['isolated_database'];runtime=support['runtime']
seed=support['seed'];deliver=support['deliver']
ACTOR=ActorContext('synthetic-human',(LineCapability.TASK_SEND.value,))
SCHEMA_SOURCE=mysql_adapter.DB_CONFIG['database']


@pytest.fixture(scope='module')
def reconciliation_schema(isolated_database):
    """Extend the owned schema only for the canonical Finance writer oracle."""
    import re
    assert re.fullmatch(r'lu_test_payment_reminders_[0-9a-f]{12}',isolated_database)
    assert re.fullmatch(r'[A-Za-z0-9_]+',SCHEMA_SOURCE) and SCHEMA_SOURCE!=isolated_database
    connection=mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            for table in ('finance_import_rows','finance_import_classification_events',
                          'client_finance_apply_receipts','order_service_data_locks'):
                cursor.execute(f'CREATE TABLE `{isolated_database}`.`{table}` LIKE `{SCHEMA_SOURCE}`.`{table}`')
    finally:
        connection.close()


@pytest.mark.parametrize('stage',['deposit','first','second'])
def test_committed_finance_apply_to_internal_notice_and_human_confirmed_private_send(
        reconciliation_schema,runtime,monkeypatch,stage):
    from api.dependencies.client_receipt_reconciliation import get_client_receipt_reconciliation_application
    from api.routes import notification_tasks, line_payment_receipt_notifications as receipt_routes
    from api.schemas.notification_tasks import NotificationSource
    from domains.client_finance.reconciliation import PaymentStage,ReconciliationStatus
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.client_finance.reconciliation_workflow import ReconciliationSelection,ClientReconciliationApplyRequest

    rt=runtime;case,obligation,user=seed(rt,stage)
    bank_row=rt.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,credit,direction,currency,bank_references,warnings,raw_payload,classification_type) VALUES (%s,'legacy','2026-11-05',24000,'incoming','TWD','{}','[]','{}','client_receipt')",(uuid4().hex+uuid4().hex,))
    rt.execute("INSERT INTO finance_import_classification_events(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) VALUES (1,%s,1,1,'client_receipt','create',%s,%s,'[]','[]','synthetic','exact obligation selection')",(bank_row,uuid4().hex+uuid4().hex,json.dumps([obligation])))
    deposit=DepositNotificationApplication(rt.units,lambda:rt.clock[0],liff_id='synthetic-liff',bank_code='807')
    app=PaymentReceiptNotificationApplication(rt.units,lambda:rt.clock[0],deposit)
    monkeypatch.setattr(notification_tasks,'get_payment_receipt_notifications',lambda:app)
    principal=AdminPrincipal(None,'synthetic-human','Synthetic human','system_admin',capabilities=frozenset((LineCapability.CUSTOMER_SERVICE_HANDLE.value,LineCapability.TASK_SEND.value)))
    def notice():
        return tuple(item for item in notification_tasks.query_source(NotificationSource.RECEIPT,0,principal).items if item.case_no==case)
    def queued():
        return rt.rows('SELECT * FROM line_delivery_tasks WHERE correlation_id LIKE %s',(case+':%',))

    selection=ReconciliationSelection(case,PaymentStage(stage),(str(bank_row),),(obligation,))
    dependency=get_client_receipt_reconciliation_application()
    try:
        finance=next(dependency)
        preview=finance.preview(selection)
        assert preview.candidate.status is ReconciliationStatus.EXACT
        assert not notice() and not queued()  # Preview is not formal reconciliation.
        request=ClientReconciliationApplyRequest(selection,ExpectedVersion(preview.account_version),preview.fingerprint,IdempotencyKey(uuid4().hex),ACTOR,'synthetic native receipt verification',CorrelationId(uuid4().hex))
        receipt=finance.apply(request)
        assert finance.apply(request)==receipt  # Replaying Apply cannot duplicate the notice.
    finally:
        dependency.close()

    settled=rt.rows('SELECT amount_due_ntd,status,projection_version FROM client_obligations WHERE obligation_identity=%s',(obligation,))[0]
    assert settled['amount_due_ntd']==0 and settled['status']=='settled'
    ledger=rt.rows('SELECT id FROM client_ledger_entries WHERE case_no=%s AND reconciliation_reference=%s',(case,receipt.settlement_identity.value))
    assert len(ledger)==1
    assert rt.rows('SELECT reconciliation_status FROM finance_import_rows WHERE id=%s',(bank_row,))[0]['reconciliation_status']=='reconciled'
    assert deposit.run_once()==0 and not queued()
    notifications=notice()
    assert len(notifications)==1 and notice()==notifications and not queued()
    notification=notifications[0]
    assert notification.tag=='待帳務確認' and notification.recipient=='客戶私人聊天室'
    assert notification.receipt.payment_stage==stage and notification.receipt.settlement_identity==receipt.settlement_identity.value
    focused=receipt_routes.list_receipts(page=1,page_size=25,case_no=case,payment_stage=stage,settlement_identity=receipt.settlement_identity.value,principal=principal,app=app).data
    assert focused['total']==1 and focused['items'][0]['can_send'] and not queued()
    assert rt.rows('SELECT amount_due_ntd,status,projection_version FROM client_obligations WHERE obligation_identity=%s',(obligation,))[0]==settled

    # Only the explicit human adapter command may create the customer task.
    payment=receipt_routes.ReceiptPayment(**focused['items'][0]['payment'])
    sent=receipt_routes.send_receipt(payment,principal=principal,app=app).data
    replay=receipt_routes.send_receipt(payment,principal=principal,app=app).data
    assert replay['task_id']==sent['task_id'] and len(queued())==1
    task=queued()[0]
    assert task['source_aggregate_type']==MANUAL_RECEIPT and task['recipient_type']=='user' and task['recipient_identity']==user
    assert len(deliver(rt,task['id']))==1  # In-process fake provider, never LINE.
    assert not notice()
    assert rt.rows('SELECT amount_due_ntd,status,projection_version FROM client_obligations WHERE obligation_identity=%s',(obligation,))[0]==settled


def prepare(rt,stage):
    case,obligation,user=seed(rt,stage);identity=uuid4().hex+uuid4().hex
    rt.execute("UPDATE client_obligations SET amount_due_ntd=0,status='settled',projection_version=2 WHERE obligation_identity=%s",(obligation,))
    ledger=rt.execute("INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) VALUES (%s,'receipt',24000,'2026-11-05',%s,%s,'synthetic','receipt fixture')",(case,identity,uuid4().hex))
    rt.execute('INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,24000,1)',(ledger,obligation))
    if stage=='deposit':
        rt.execute("INSERT INTO client_deposit_settlement_projection(case_no,deposit_obligation_identity,settlement_state,settlement_identity,contracted_amount_ntd,allocated_net_amount_ntd,latest_ledger_entry_id,source_fingerprint,projection_version) VALUES (%s,%s,'settled',%s,24000,24000,%s,REPEAT('a',64),1)",(case,obligation,identity,ledger))
    payload={'settlement_identity':identity,'amount_ntd':24000,'obligation_identities':[obligation],('line_deposit_notification' if stage=='deposit' else f'line_{stage}_payment_notification'):True}
    if stage=='first':
        from infrastructure.mysql.client_receipt_reconciliation_repository import _append_projection_outbox
        from domains.client_finance.reconciliation import PaymentStage
        request=SimpleNamespace(selection=SimpleNamespace(case_no=case,payment_stage=PaymentStage.FIRST,obligation_identities=(obligation,)),idempotency_key=IdempotencyKey(uuid4().hex))
        with rt.units() as unit:
            with unit._connection.cursor() as cursor:_append_projection_outbox(cursor,request,identity,2,{obligation:24000})
            unit.commit()
    else:
        rt.execute('INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) VALUES (%s,%s,%s,%s)',(case,'orders_deposit_reconciled' if stage=='deposit' else 'projection_refresh',uuid4().hex,json.dumps(payload)))
    deposit=DepositNotificationApplication(rt.units,lambda:rt.clock[0],liff_id='synthetic-liff',bank_code='807')
    app=PaymentReceiptNotificationApplication(rt.units,lambda:rt.clock[0],deposit)
    return app,case,obligation,user,identity,deposit


@pytest.mark.parametrize('stage',['deposit','first','second'])
def test_native_human_only_private_send_unique_and_keeps_finance_untouched(runtime,stage):
    rt=runtime;app,case,obligation,user,identity,deposit=prepare(rt,stage)
    before=rt.rows('SELECT * FROM client_obligations WHERE obligation_identity=%s',(obligation,))
    assert deposit.run_once()==0
    items,_=app.list();item=next(item for item in items if item.payment.case_no==case)
    assert item.can_send and not rt.rows('SELECT id FROM line_delivery_tasks WHERE correlation_id LIKE %s',(case+':%',))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:app.send(item.payment,ACTOR),range(2)))
    assert results[0][0]==results[1][0]
    task=rt.rows('SELECT * FROM line_delivery_tasks WHERE id=%s',(results[0][0],))[0]
    assert task['source_aggregate_type']==MANUAL_RECEIPT and task['recipient_type']=='user' and task['recipient_identity']==user
    assert len(deliver(rt,task['id']))==1
    assert not any(row.payment.case_no==case for row in app.list()[0])
    assert rt.rows('SELECT * FROM client_obligations WHERE obligation_identity=%s',(obligation,))==before


@pytest.mark.parametrize('stage',['deposit','first','second'])
@pytest.mark.parametrize('change',['unbound','amount','reversed','cancelled'])
def test_native_provider_rechecks_receipt_and_binding(runtime,stage,change):
    rt=runtime;app,case,obligation,user,identity,_=prepare(rt,stage)
    item=next(row for row in app.list()[0] if row.payment.case_no==case)
    task=app.send(item.payment,ACTOR)[0]
    if change=='unbound':rt.execute("UPDATE line_identity_role_bindings SET binding_status='revoked' WHERE line_user_id=%s",(user,))
    elif change=='cancelled':rt.execute("UPDATE orders SET status='訂單取消' WHERE case_no=%s",(case,))
    elif change=='amount':rt.execute('UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,)) if stage!='deposit' else rt.execute('UPDATE client_obligations SET projection_version=projection_version+1 WHERE obligation_identity=%s',(obligation,))
    elif stage=='deposit':rt.execute("UPDATE client_deposit_settlement_projection SET settlement_state='unsettled',settlement_identity=NULL,allocated_net_amount_ntd=0 WHERE case_no=%s",(case,))
    else:rt.execute("UPDATE client_ledger_entries SET entry_type='refund' WHERE case_no=%s AND reconciliation_reference=%s",(case,identity))
    assert deliver(rt,task)==[]
    assert rt.rows('SELECT processing_status FROM line_delivery_tasks WHERE id=%s',(task,))[0]['processing_status']=='cancelled'


def test_native_stale_permission_no_history_backfill_and_old_auto_cancel(runtime):
    rt=runtime;app,case,obligation,user,identity,deposit=prepare(rt,'deposit')
    item=next(row for row in app.list()[0] if row.payment.case_no==case)
    with pytest.raises(LineCapabilityDeniedError):app.send(item.payment,ActorContext('reader'))
    with pytest.raises(PaymentReceiptConflict):app.send(replace(item.payment,amount_ntd=1),ACTOR)
    with rt.units() as unit:
        payment=unit.deposit_payments.get(case)
        task=unit.delivery_tasks.enqueue(deposit._request(payment,user,SETTLED,settlement_key(payment),unit));unit.commit()
    assert deliver(rt,task.task_id.value)==[]
    assert any(row.payment.case_no==case for row in app.list()[0])
    rt.execute("DELETE FROM client_finance_outbox WHERE case_no=%s",(case,))
    assert not any(row.payment.case_no==case for row in app.list()[0])


def test_first_receipt_requires_full_valid_settlement_and_marked_commit(runtime):
    rt=runtime;app,case,obligation,_,identity,_=prepare(rt,'first')
    item=next(row for row in app.list()[0] if row.payment.case_no==case)
    marker=rt.rows("SELECT payload_snapshot FROM client_finance_outbox WHERE case_no=%s",(case,))[0]['payload_snapshot']
    assert json.loads(marker)['line_first_payment_notification'] is True
    assert item.payment.payment_stage=='first'
    rt.execute("UPDATE client_obligations SET amount_due_ntd=1000,status='open' WHERE obligation_identity=%s",(obligation,))
    assert not app.list(case_no=case)[0]
    with pytest.raises(PaymentReceiptConflict):app.send(item.payment,ACTOR)
    rt.execute("UPDATE client_obligations SET amount_due_ntd=0,status='settled' WHERE obligation_identity=%s",(obligation,))
    rt.execute("UPDATE client_finance_outbox SET payload_snapshot=JSON_REMOVE(payload_snapshot,'$.line_first_payment_notification') WHERE case_no=%s",(case,))
    assert not app.list(case_no=case)[0]  # No historical backfill without a marked commit.


def test_focused_receipt_query_never_substitutes_another_case_or_stage(runtime):
    rt=runtime;app,case,_,_,identity,_=prepare(rt,'first')
    assert len(app.list(case_no=case,payment_stage='first',settlement_identity=identity)[0])==1
    assert app.list(case_no=case,payment_stage='second',settlement_identity=identity)==((),0)
    assert app.list(case_no='NON-EXISTENT',payment_stage='first',settlement_identity=identity)==((),0)

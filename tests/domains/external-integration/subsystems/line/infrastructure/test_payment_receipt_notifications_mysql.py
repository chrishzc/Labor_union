"""Native isolated DB oracle: reads/worker scans never send; only human commands do."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
from datetime import date
import json,runpy,pytest
from shared_kernel.identities import ActorContext,IdempotencyKey
from subsystems.line.capabilities import LineCapability,LineCapabilityDeniedError
from subsystems.line.deposit_notifications import DepositNotificationApplication,SETTLED,settlement_key
from subsystems.line.payment_receipt_notifications import PaymentReceiptNotificationApplication,PaymentReceiptConflict,MANUAL_RECEIPT,receipt_snapshot

support=runpy.run_path('tests/domains/external-integration/subsystems/line/infrastructure/test_payment_reminder_notifications_mysql.py')
pytestmark=support['pytestmark'];isolated_database=support['isolated_database'];runtime=support['runtime']
seed=support['seed'];deliver=support['deliver']
ACTOR=ActorContext('synthetic-human',(LineCapability.TASK_SEND.value,))


def prepare(rt,stage):
    case,obligation,user=seed(rt,stage);identity=uuid4().hex+uuid4().hex
    rt.execute("UPDATE client_obligations SET amount_due_ntd=0,status='settled',projection_version=2 WHERE obligation_identity=%s",(obligation,))
    ledger=rt.execute("INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) VALUES (%s,'receipt',24000,'2026-11-05',%s,%s,'synthetic','receipt fixture')",(case,identity,uuid4().hex))
    rt.execute('INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,24000,1)',(ledger,obligation))
    if stage=='deposit':
        rt.execute("INSERT INTO client_deposit_settlement_projection(case_no,deposit_obligation_identity,settlement_state,settlement_identity,contracted_amount_ntd,allocated_net_amount_ntd,latest_ledger_entry_id,source_fingerprint,projection_version) VALUES (%s,%s,'settled',%s,24000,24000,%s,REPEAT('a',64),1)",(case,obligation,identity,ledger))
    payload={'settlement_identity':identity,'amount_ntd':24000,'obligation_identities':[obligation],('line_deposit_notification' if stage=='deposit' else 'line_second_payment_notification'):True}
    rt.execute('INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) VALUES (%s,%s,%s,%s)',(case,'orders_deposit_reconciled' if stage=='deposit' else 'projection_refresh',uuid4().hex,json.dumps(payload)))
    deposit=DepositNotificationApplication(rt.units,lambda:rt.clock[0],liff_id='synthetic-liff',bank_code='807')
    app=PaymentReceiptNotificationApplication(rt.units,lambda:rt.clock[0],deposit)
    return app,case,obligation,user,identity,deposit


@pytest.mark.parametrize('stage',['deposit','second'])
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


@pytest.mark.parametrize('stage',['deposit','second'])
@pytest.mark.parametrize('change',['unbound','amount','reversed','cancelled'])
def test_native_provider_rechecks_receipt_and_binding(runtime,stage,change):
    rt=runtime;app,case,obligation,user,identity,_=prepare(rt,stage)
    item=next(row for row in app.list()[0] if row.payment.case_no==case)
    task=app.send(item.payment,ACTOR)[0]
    if change=='unbound':rt.execute("UPDATE line_identity_role_bindings SET binding_status='revoked' WHERE line_user_id=%s",(user,))
    elif change=='cancelled':rt.execute("UPDATE orders SET status='訂單取消' WHERE case_no=%s",(case,))
    elif change=='amount':rt.execute('UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,)) if stage=='second' else rt.execute('UPDATE client_obligations SET projection_version=projection_version+1 WHERE obligation_identity=%s',(obligation,))
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

"""Real Finance -> committed source -> group delivery, using a task-scoped fake provider.

Explicit localhost lu_test_ target only. Source facts are built with actual
intake, service-start and bank-import writers. No live LINE runtime is started.
"""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
import json
import os
import runpy
import pytest

from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.order_pre_start_notification_source_worker import MySqlOrderPreStartNotificationSourceWorker
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository
from subsystems.line.second_payment_notifications import REMINDER, SETTLED, DUE_EVENT, SETTLED_EVENT

DATABASE=os.getenv('SERVICE_START_TEST_DB')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicit disposable localhost database')
support=runpy.run_path('tests/domains/external-integration/subsystems/line/infrastructure/test_service_start_day_mysql.py')
http=support['http'];configurations=support['configurations']
rows,write,checked,units=support['rows'],support['write'],support['checked'],support['units']
existing=support['existing']
START=date(2032,5,4);DUE=START+timedelta(days=15)
NOW=datetime.combine(DUE,datetime.min.time(),tzinfo=timezone.utc)+timedelta(hours=3)


def prepared(http):
    case,staff,segments=existing['seed_case'](http)
    checked(existing['submit'](http,case,staff[0],segments[0],start=START.isoformat())[0])
    assert rows('SELECT second_payment_due_date FROM client_payment_terms WHERE case_no=%s',(case,))[0]['second_payment_due_date']==DUE
    return case,staff,segments


def scan(now=NOW):
    return MySqlOrderPreStartNotificationSourceWorker(mysql_adapter.get_connection,lambda:now).run_once()


def current(case):
    with units() as unit:return unit.second_payment_notifications.current(case)


def tasks(case,kind=REMINDER):
    return rows('SELECT * FROM line_delivery_tasks WHERE source_aggregate_type=%s AND source_aggregate_identity=%s ORDER BY id',(kind,case))


def pay(http,case,sequence=2):
    amount=current(case).remaining_amount
    existing['h']['bank'](http,case,amount,sequence)
    return amount


def deliver(task_id,now=NOW):
    worker=support['TaskScopedWorker'](task_id,now=now)
    worker.run_once()
    return worker.calls


def test_due_today_group_only_dedup_and_successful_fake_delivery(http):
    case,_,_=prepared(http)
    before=rows('SELECT lifecycle_version,status FROM orders WHERE case_no=%s',(case,))
    scan(NOW-timedelta(days=1));assert not tasks(case)
    scan();scan();work=tasks(case);assert len(work)==1
    assert work[0]['recipient_type']=='group' and work[0]['recipient_identity']==current(case).group_id
    text=json.loads(work[0]['payload_snapshot'])['text']
    assert '請於今天完成繳款' in text and '即將圓滿完成' not in text
    assert len(deliver(work[0]['id']))==1
    scan();assert len(tasks(case))==1
    assert rows('SELECT lifecycle_version,status FROM orders WHERE case_no=%s',(case,))==before


def test_paid_before_due_no_reminder_and_one_committed_group_success(http):
    case,_,_=prepared(http)
    amount=pay(http,case)
    assert current(case).remaining_amount==0
    markers=rows("SELECT id,status,payload_snapshot FROM client_finance_outbox WHERE case_no=%s AND intent_type='projection_refresh' AND JSON_EXTRACT(payload_snapshot,'$.line_second_payment_notification')=TRUE",(case,))
    assert len(markers)==1
    marker=json.loads(markers[0]['payload_snapshot'])
    assert marker['amount_ntd']==amount and marker['payment_stage']=='second'
    assert not rows("SELECT id FROM client_finance_outbox WHERE case_no=%s AND intent_type='anomaly_review_required'",(case,))
    scan(NOW-timedelta(days=1));scan()
    assert not tasks(case)
    work=tasks(case,SETTLED);assert len(work)==1
    assert json.loads(work[0]['payload_snapshot'])=={'type':'text','text':f'案件 {case} 第二期款 {amount:,} 元已確認入帳，謝謝。'}
    assert work[0]['recipient_type']=='group'
    assert len(deliver(work[0]['id']))==1
    # A subsequent first-stage receipt changes Finance version, not the identity
    # of the already-notified second-stage settlement.
    first=rows("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='first' AND status='open'",(case,))[0]['amount_due_ntd']
    existing['h']['bank'](http,case,first,3)
    scan();assert len(tasks(case,SETTLED))==1
    assert rows('SELECT status FROM client_finance_outbox WHERE id=%s',(markers[0]['id'],))[0]['status']==markers[0]['status']


def test_payment_between_queue_and_send_cancels_reminder_and_queues_receipt(http):
    case,_,_=prepared(http);scan();old=tasks(case)[0]
    pay(http,case)
    assert not deliver(old['id'])
    assert tasks(case)[0]['processing_status']=='cancelled'
    scan();assert len(tasks(case))==1 and len(tasks(case,SETTLED))==1


@pytest.mark.parametrize('change',['reschedule','group','rebind_same_group','cancel'])
def test_fresh_read_cancels_obsolete_reminder(http,change):
    case,staff,segments=prepared(http);scan();old=tasks(case)[0]
    if change=='reschedule':
        checked(existing['submit'](http,case,staff[0],segments[0],start=(START+timedelta(days=2)).isoformat())[0])
    elif change=='group':
        # A different effective binding is an explicit synthetic prerequisite;
        # no actual group command or external invitation is executed.
        write('UPDATE line_order_group_bindings SET group_id=%s,aggregate_version=aggregate_version+1 WHERE case_no=%s',('C'+uuid4().hex,case))
    elif change=='rebind_same_group':
        write('UPDATE line_order_group_bindings SET aggregate_version=aggregate_version+2 WHERE case_no=%s',(case,))
    else:
        write("UPDATE orders SET status='訂單取消',lifecycle_version=lifecycle_version+1 WHERE case_no=%s",(case,))
    assert not deliver(old['id'])
    assert tasks(case)[0]['processing_status']=='cancelled'
    scan();assert len(tasks(case))==(2 if change in ('group','rebind_same_group') else 1)
    if change=='reschedule':
        scan(NOW+timedelta(days=2));assert len(tasks(case))==2


def test_missing_group_is_a_line_staff_todo_and_never_private(http):
    case,_,_=prepared(http)
    write("UPDATE line_order_group_bindings SET binding_status='released',aggregate_version=aggregate_version+1 WHERE case_no=%s",(case,))
    scan();assert not tasks(case)
    decisions=rows('SELECT d.reason_code FROM line_notification_source_events s JOIN line_notification_decisions d ON d.source_event_id=s.id WHERE s.event_code=%s AND s.source_aggregate_identity=%s',(DUE_EVENT,case))
    assert decisions and decisions[0]['reason_code']=='recipient_unavailable'
    with units() as unit:
        assert any(item.case_no==case for item in unit.notification_rules.list_line006_recheck_targets(limit=100))
    # Even a valid new settlement waits for a group; no private receipt fallback.
    pay(http,case);scan();assert not tasks(case,SETTLED)


def test_no_second_payment_never_creates_a_source_or_notification(http):
    case='116'+str(rows('SELECT COUNT(*) n FROM orders')[0]['n']+1).zfill(6)
    client=write("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic no second','一般市民','連續服務','2026-10-01')",(case,))
    write("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,%s,10,8,0,'08:00:00','17:00:00',0)",(case,client,START))
    url=f'/api/v1/orders/{case}/intake-completion'
    preview=checked(http.post(url+'/preview',json={}))
    checked(http.post(url+'/apply',json={'expected_lifecycle_version':preview['lifecycle_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':uuid4().hex}))
    assert rows('SELECT second_payment_due_date FROM client_payment_terms WHERE case_no=%s',(case,))[0]['second_payment_due_date'] is None
    assert current(case) is None
    # An obsolete saved date alone must not manufacture a second-stage charge.
    write('UPDATE client_payment_terms SET second_payment_due_date=%s WHERE case_no=%s',(DUE,case))
    assert current(case) is None
    scan()
    assert not tasks(case) and not tasks(case,SETTLED)
    assert not rows('SELECT id FROM line_notification_source_events WHERE source_aggregate_identity=%s AND event_code IN (%s,%s)',(case,DUE_EVENT,SETTLED_EVENT))


def test_reconciliation_failure_rolls_back_marker_ledger_and_notice(http,monkeypatch):
    case,_,_=prepared(http)
    original=MySqlClientReceiptReconciliationRepository.save_receipt
    def fail_after_finance_writes(repository,key,receipt):
        if repository._request.selection.payment_stage.value=='second':
            raise RuntimeError('synthetic rollback after projection outbox')
        return original(repository,key,receipt)
    with monkeypatch.context() as patch:
        patch.setattr(MySqlClientReceiptReconciliationRepository,'save_receipt',fail_after_finance_writes)
        with pytest.raises(AssertionError):pay(http,case)
    assert current(case).remaining_amount>0
    assert not rows("SELECT id FROM client_finance_outbox WHERE case_no=%s AND JSON_EXTRACT(payload_snapshot,'$.line_second_payment_notification')=TRUE",(case,))
    assert not rows("SELECT l.id FROM client_ledger_entries l JOIN client_ledger_obligation_allocations a ON a.ledger_entry_id=l.id JOIN client_obligations o ON o.obligation_identity=a.obligation_identity WHERE l.case_no=%s AND o.obligation_type='second'",(case,))
    scan();assert not tasks(case,SETTLED)


def test_reversed_receipt_ledger_cancels_success_even_with_stale_settled_projection(http):
    case,_,_=prepared(http);amount=pay(http,case);scan();old=tasks(case,SETTLED)[0]
    original=rows("SELECT l.id,o.obligation_identity FROM client_ledger_entries l JOIN client_ledger_obligation_allocations a ON a.ledger_entry_id=l.id JOIN client_obligations o ON o.obligation_identity=a.obligation_identity WHERE l.case_no=%s AND o.obligation_type='second' AND l.entry_type='receipt'",(case,))[0]
    # Deliberately lag the settled projection behind an immutable reversal fact.
    # There is no general second-receipt reversal API introduced by this change.
    with units() as unit:
        with unit._connection.cursor() as cursor:
            cursor.execute("INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) VALUES (%s,'reversal',%s,%s,%s,%s,%s,'synthetic','guard verification')",(case,amount,DUE,uuid4().hex,original['id'],uuid4().hex))
            cursor.execute('INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,%s,1)',(cursor.lastrowid,original['obligation_identity'],amount))
        unit.commit()
    assert current(case).settled
    assert not deliver(old['id'])
    assert tasks(case,SETTLED)[0]['processing_status']=='cancelled'


def test_no_longer_required_second_stage_cancels_pending_success(http):
    case,_,_=prepared(http);pay(http,case);scan();old=tasks(case,SETTLED)[0]
    # Explicit no-second terms fixture, leaving immutable paid history intact.
    write('UPDATE client_payment_terms SET second_payment_due_date=NULL WHERE case_no=%s',(case,))
    assert current(case) is None
    assert not deliver(old['id'])
    scan();assert len(tasks(case,SETTLED))==1
    assert tasks(case,SETTLED)[0]['processing_status']=='cancelled'


def test_historical_unmarked_receipt_is_not_backfilled(http,monkeypatch):
    import infrastructure.mysql.client_receipt_reconciliation_repository as owner
    case,_,_=prepared(http)
    def old_projection(cursor,request,identity,version,amounts):
        # The exact pre-change source shape, through the real Finance UoW.
        cursor.execute(owner._OUTBOX_INSERT_SQL,(request.selection.case_no,'projection_refresh',
            'historical-second:'+uuid4().hex,json.dumps({'case_no':case,'settlement_identity':identity,'resulting_account_version':version})))
    with monkeypatch.context() as patch:
        patch.setattr(owner,'_append_projection_outbox',old_projection)
        pay(http,case)
    assert current(case).settled
    scan();assert not tasks(case) and not tasks(case,SETTLED)


def test_projection_uses_fresh_facts_after_initial_repeatable_read_snapshot(http,monkeypatch):
    from infrastructure.mysql.second_payment_query_repository import MySqlSecondPaymentQueryRepository
    case,_,_=prepared(http)
    original=MySqlSecondPaymentQueryRepository.get
    changed=[]
    def concurrent_version_commit(repository,case_no,*,lock=False):
        if case_no==case and lock and not changed:
            changed.append(True)
            # Simulate a writer committing after the source worker's initial
            # date scan, before its Finance lock. Old RR reads must not suppress
            # the new authoritative source snapshot permanently.
            write('UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
        return original(repository,case_no,lock=lock)
    monkeypatch.setattr(MySqlSecondPaymentQueryRepository,'get',concurrent_version_commit)
    scan()
    assert changed and len(tasks(case))==1
    assert len(deliver(tasks(case)[0]['id']))==1

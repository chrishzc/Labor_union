"""Deposit notifications preserve finance truth, customer ownership and durable delivery."""
from dataclasses import replace
from datetime import date, datetime, timezone, timedelta
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId, LineUserId, LineSourceType
from domains.client_finance.reconciliation import PaymentStage
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository
from infrastructure.mysql.deposit_payment_query_repository import MySqlDepositPaymentQueryRepository
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from infrastructure.mysql.overdue_payment_query_repository import MySqlOverduePaymentQueryRepository
from infrastructure.mysql.payment_overdue_reminder_repository import MySqlPaymentOverdueReminderRepository
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.customer_service_repository import MySqlCustomerServiceRepository
from infrastructure.mysql.line_receipt_outbox_audit import MySqlLineAuditRepository
from shared_kernel.identities import ActorContext, IdempotencyKey
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.line.capabilities import LineCapability
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.deposit_notifications import (
    ASSISTANCE_ACK, DepositNotificationApplication, DepositNotificationConflict,
    DepositPaymentForbidden, handle_deposit_assistance, payment_source,
)
from subsystems.line.payment_overdue_reminders import PaymentOverdueReminderApplication, PaymentOverdueReminderConflict

NOW = datetime(2026, 10, 22, 5, tzinfo=timezone.utc)
CASE = '115000157'
USER = 'U-synthetic-deposit-customer'
ACTOR = ActorContext('admin:3', (LineCapability.TASK_SEND.value,))


class Cursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()

    def execute(self, sql, parameters=()):
        sql = sql.replace('CAST(c.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci', 'CAST(c.id AS TEXT)')
        sql = sql.replace(' FOR UPDATE SKIP LOCKED', '').replace(' FOR UPDATE', '').replace('%s', '?').replace('%%', '%')
        self.cursor.execute(sql, tuple(value.isoformat(' ') if isinstance(value, datetime) else value for value in parameters))
        self.lastrowid, self.rowcount = self.cursor.lastrowid, self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return self._row(row)

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]

    @staticmethod
    def _row(row):
        return {key: (datetime.fromisoformat(value) if key.endswith('_at_utc') else
                      date.fromisoformat(value) if key == 'due_date' else value) if value else value
                for key, value in dict(row).items()}


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def cursor(self):
        return Cursor(self.raw)


class Uow:
    def __init__(self, raw):
        self.raw = raw
        connection = Connection(raw)
        self.deposit_payments = MySqlDepositPaymentQueryRepository(connection)
        self.deposit_notifications = MySqlDepositNotificationRepository(connection)
        self.payment_overdue_reminders = MySqlPaymentOverdueReminderRepository(connection)
        self.delivery_tasks = MySqlLineDeliveryTaskRepository(connection)
        self.audit = MySqlLineAuditRepository(connection)
        self.customer_service = SimpleNamespace(create_or_append=lambda command: SimpleNamespace(ticket_id=55))

    def __enter__(self):
        self.committed = False
        return self

    def __exit__(self, *_):
        if not self.committed:
            self.raw.rollback()

    def commit(self):
        self.raw.commit()
        self.committed = True


@pytest.fixture
def db():
    raw = sqlite3.connect(':memory:', check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.create_function('JSON_UNQUOTE', 1, lambda value: value)
    raw.create_function('CONCAT', -1, lambda *values: ''.join(str(value) for value in values))
    raw.executescript('''
    CREATE TABLE orders(case_no TEXT PRIMARY KEY,client_id INTEGER,status TEXT,contract_identity TEXT);
    CREATE TABLE order_contract_flow_events(case_no TEXT,contract_identity TEXT,event_type TEXT);
    CREATE TABLE client_finance_accounts(case_no TEXT PRIMARY KEY,aggregate_version INTEGER);
    CREATE TABLE line_order_group_bindings(case_no TEXT,group_id TEXT,binding_status TEXT,aggregate_version INTEGER);
    CREATE TABLE clients(id INTEGER PRIMARY KEY,line_user_id TEXT);
    CREATE TABLE line_identity_role_bindings(line_user_id TEXT,subject_type TEXT,subject_reference TEXT,binding_status TEXT);
    CREATE TABLE client_obligations(obligation_identity TEXT PRIMARY KEY,case_no TEXT,obligation_type TEXT,direction TEXT,
        status TEXT,projection_version INTEGER,amount_due_ntd INTEGER,due_date TEXT,current_event_id INTEGER);
    CREATE TABLE client_obligation_events(id INTEGER PRIMARY KEY AUTOINCREMENT,obligation_identity TEXT,after_amount_ntd INTEGER);
    CREATE TRIGGER seed_obligation_lineage AFTER INSERT ON client_obligations BEGIN
      INSERT INTO client_obligation_events(obligation_identity,after_amount_ntd) VALUES (NEW.obligation_identity,NEW.amount_due_ntd);
      UPDATE client_obligations SET current_event_id=last_insert_rowid() WHERE obligation_identity=NEW.obligation_identity;
    END;
    CREATE TABLE client_deposit_settlement_projection(case_no TEXT PRIMARY KEY,deposit_obligation_identity TEXT,
        settlement_state TEXT,settlement_identity TEXT,contracted_amount_ntd INTEGER,allocated_net_amount_ntd INTEGER,latest_ledger_entry_id INTEGER);
    CREATE TABLE client_ledger_entries(id INTEGER PRIMARY KEY,case_no TEXT,entry_type TEXT,occurred_on TEXT);
    CREATE TABLE client_legacy_virtual_accounts(case_no TEXT,virtual_account TEXT);
    CREATE TABLE client_finance_outbox(id INTEGER PRIMARY KEY,case_no TEXT,intent_type TEXT CHECK(intent_type IN
        ('orders_deposit_reconciled','orders_deposit_reversed','anomaly_review_required','projection_refresh')),intent_key TEXT UNIQUE,
        payload_snapshot TEXT,status TEXT DEFAULT 'pending',next_attempt_at TEXT,delivered_at TEXT,last_error TEXT);
    CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY,recipient_type TEXT,recipient_identity TEXT,message_kind TEXT,
        payload_snapshot TEXT,payload_fingerprint TEXT,scheduled_at_utc TEXT,source_aggregate_type TEXT,source_aggregate_identity TEXT,
        idempotency_key TEXT UNIQUE,correlation_id TEXT,processing_status TEXT DEFAULT 'pending',completed_attempts INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3,next_attempt_at_utc TEXT,lease_owner TEXT,lease_acquired_at_utc TEXT,lease_expires_at_utc TEXT);
    CREATE TABLE customer_service_tickets(id INTEGER PRIMARY KEY,line_user_id TEXT,category TEXT,status TEXT,version INTEGER,case_no TEXT);
    CREATE TABLE customer_service_ticket_events(ticket_id INTEGER,event_key TEXT);
    CREATE TABLE line_domain_audit_events(action TEXT,actor_id TEXT,aggregate_type TEXT,aggregate_identity TEXT);
    ''')
    raw.execute("INSERT INTO orders(case_no,client_id,status) VALUES (?,1,'洽談中')", (CASE,))
    complete_contract(raw)
    raw.execute('INSERT INTO client_finance_accounts VALUES (?,2)', (CASE,))
    raw.execute("INSERT INTO line_order_group_bindings VALUES (?,'C-synthetic','active',1)", (CASE,))
    raw.execute('INSERT INTO clients VALUES (1,?)', (USER,))
    raw.execute("INSERT INTO line_identity_role_bindings VALUES (?,'customer','1','bound')", (USER,))
    raw.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,status,projection_version,amount_due_ntd,due_date) VALUES ('deposit-one',?,'deposit','receivable_from_client','open',2,12000,'2026-11-01')", (CASE,))
    raw.commit()
    yield raw
    raw.close()


def application(db, **kwargs):
    return DepositNotificationApplication(lambda: Uow(db), lambda: NOW, liff_id='synthetic-liff', bank_code=kwargs.get('bank_code', '807'))


def complete_contract(db, case_no=CASE):
    identity = case_no + ':signed'
    db.execute('UPDATE orders SET contract_identity=? WHERE case_no=?', (identity, case_no))
    db.execute("INSERT INTO order_contract_flow_events VALUES (?,?,'contract_completed')", (case_no, identity))


@pytest.mark.parametrize('change', ['missing_event', 'missing_identity', 'different_contract', 'different_case'])
def test_unsigned_contract_keeps_calculated_amount_but_blocks_reminder_list_and_send(db, change):
    if change == 'missing_event':
        db.execute('DELETE FROM order_contract_flow_events')
    elif change == 'missing_identity':
        db.execute('UPDATE orders SET contract_identity=NULL')
    elif change == 'different_contract':
        db.execute("UPDATE orders SET contract_identity='other-contract'")
    else:
        db.execute("UPDATE order_contract_flow_events SET case_no='other-case'")
    db.commit()
    before = rows(db, 'client_obligations')
    page = Uow(db).deposit_notifications.followups()
    assert page.items == () and page.total == page.unpaid_total == page.page_total == 0
    assert application(db).query_customer(CASE, USER).amount_ntd == 12000
    with pytest.raises(DepositNotificationConflict, match='deposit_contract_not_completed'):
        application(db).send_reminder(CASE, 2, IdempotencyKey('unsigned'), ACTOR)
    assert not rows(db, 'line_delivery_tasks') and rows(db, 'client_obligations') == before


@pytest.mark.parametrize('stage', ['deposit', 'first', 'second'])
def test_all_overdue_stages_require_both_parties_signed_at_query_send_and_provider(db, stage):
    db.execute('UPDATE client_obligations SET obligation_type=?,due_date=?', (stage, '2026-10-21'))
    db.commit()
    repository = MySqlOverduePaymentQueryRepository(Connection(db))
    payments, total = repository.list(date(2026, 10, 22), 1, 25)
    assert total == 1 and len(payments) == 1 and payments[0].payment_stage == stage
    expected = payments[0]
    app = PaymentOverdueReminderApplication(lambda: Uow(db), lambda: NOW)
    identity, _ = app.send(expected, 'signed-' + stage, ACTOR)
    db.execute('DELETE FROM order_contract_flow_events')
    db.commit()
    before = rows(db, 'client_obligations')
    assert repository.list(date(2026, 10, 22), 1, 25) == ((), 0)
    assert repository.get(expected.obligation_identity, lock=True) is None
    with pytest.raises(PaymentOverdueReminderConflict, match='payment_overdue_changed'):
        app.send(expected, 'unsigned-' + stage, ACTOR)
    db.execute("UPDATE line_delivery_tasks SET processing_status='processing',lease_owner='test',lease_acquired_at_utc=?,lease_expires_at_utc=?",
               (NOW.isoformat(' '), (NOW + timedelta(seconds=60)).isoformat(' ')))
    db.commit()
    task = Uow(db).delivery_tasks.get(LineDeliveryTaskId(identity))
    worker = LineDeliveryWorker(lambda: Uow(db), SimpleNamespace(send=lambda _: pytest.fail('unsigned case reached provider')),
                                'test', lambda: NOW, batch_size=1)
    worker._claim = lambda: (task,)
    assert worker.run_once() == 1
    assert rows(db, 'line_delivery_tasks')[0]['processing_status'] == 'cancelled'
    assert rows(db, 'client_obligations') == before
    complete_contract(db)
    db.commit()
    assert repository.list(date(2026, 10, 22), 1, 25)[1] == 1


@pytest.mark.parametrize('liff_id',['','your_liff_id_here'])
def test_missing_payment_page_disables_reminder_before_enqueue(db,liff_id):
    app=DepositNotificationApplication(lambda:Uow(db),lambda:NOW,liff_id=liff_id,bank_code='807')
    payment=MySqlDepositPaymentQueryRepository(Connection(db)).get(CASE)
    assert not app.ready(payment)
    before=db.execute('SELECT COUNT(*) FROM line_delivery_tasks').fetchone()[0]
    with pytest.raises(DepositNotificationConflict):app.send_reminder(CASE,payment.obligation_version,IdempotencyKey('missing-page'),ACTOR)
    assert db.execute('SELECT COUNT(*) FROM line_delivery_tasks').fetchone()[0]==before


def settle(db, *, commit=True):
    db.execute('INSERT INTO client_ledger_entries VALUES (1,?,\'receipt\',\'2026-10-20\')', (CASE,))
    db.execute("INSERT INTO client_deposit_settlement_projection VALUES (?,'deposit-one','settled',?,12000,12000,1)", (CASE, 'a' * 64))
    db.execute("UPDATE client_obligations SET amount_due_ntd=0,status='settled' WHERE obligation_identity='deposit-one'")
    repository = MySqlClientReceiptReconciliationRepository(Connection(db))
    repository._request = SimpleNamespace(selection=SimpleNamespace(case_no=CASE,payment_stage=PaymentStage.DEPOSIT),
        expected_account_version=SimpleNamespace(value=2), idempotency_key=IdempotencyKey('synthetic-settlement'))
    repository.append_orders_deposit_intent(SimpleNamespace(settlement_identity=PreviewFingerprint('a' * 64)))
    if commit:
        db.commit()


def rows(db, table):
    return tuple(dict(row) for row in db.execute('SELECT * FROM ' + table))


def test_reminder_creates_committed_job_with_exact_text_and_buttons_no_finance_write(db):
    before = rows(db, 'client_obligations')
    task, status = application(db).send_reminder(CASE, 2, IdempotencyKey('one'), ACTOR)
    assert status == 'pending' and task == 1
    job, = rows(db, 'line_delivery_tasks')
    payload = json.loads(job['payload_snapshot'])
    assert payload['altText'] == '案件〈115000157〉訂金 NT$12,000，請於2026-11-01前完成匯款。'
    actions = payload['contents']['footer']['contents']
    assert actions[0]['action']['label'] == '查看繳費資訊'
    assert 'target=deposit_payment' in actions[0]['action']['uri'] and 'case_no=115000157' in actions[0]['action']['uri']
    assert actions[1]['action'] == {'type':'postback','label':'專人協助','data':'deposit-assistance:115000157'}
    assert '99781699' not in job['payload_snapshot']
    assert rows(db, 'client_obligations') == before and not rows(db, 'client_ledger_entries')
    assert application(db).send_reminder(CASE, 2, IdempotencyKey('one'), ACTOR) == (task, status)
    assert len(rows(db, 'line_delivery_tasks')) == 1
    audit, = rows(db,'line_domain_audit_events')
    assert audit['actor_id'] == ACTOR.actor_id and audit['action']=='deposit_reminder_queued'


@pytest.mark.parametrize('change', ['settled','version','account','deadline','binding','bank','no-capability'])
def test_reminder_blocks_changed_missing_or_unauthorized_facts_without_job(db, change):
    app = application(db)
    actor = ACTOR
    if change == 'settled': settle(db)
    if change == 'version': db.execute('UPDATE client_obligations SET projection_version=3')
    if change == 'account': db.execute("UPDATE orders SET case_no='CASE-NONCANONICAL'");db.execute("UPDATE client_obligations SET case_no='CASE-NONCANONICAL'")
    if change == 'deadline': db.execute('UPDATE client_obligations SET due_date=NULL')
    if change == 'binding': db.execute("UPDATE line_identity_role_bindings SET binding_status='suspended'")
    if change == 'bank': app = application(db, bank_code='')
    if change == 'no-capability': actor = ActorContext('customer')
    db.commit()
    with pytest.raises((DepositNotificationConflict, PermissionError)):
        app.send_reminder('CASE-NONCANONICAL' if change == 'account' else CASE, 2, IdempotencyKey('one'), actor)
    assert not rows(db, 'line_delivery_tasks')


def test_success_is_automatic_only_for_committed_formal_deposit_and_replay_is_unique(db):
    # A legitimate receipt before signing still gets its receipt notification.
    db.execute('DELETE FROM order_contract_flow_events')
    db.execute('UPDATE orders SET contract_identity=NULL')
    db.commit()
    assert application(db).run_once() == 0
    settle(db)
    assert {row['intent_type'] for row in rows(db,'client_finance_outbox')} == {'orders_deposit_reconciled'}
    assert json.loads(rows(db,'client_finance_outbox')[0]['payload_snapshot'])['line_deposit_notification'] is True
    assert application(db).run_once() == 1
    job, = rows(db, 'line_delivery_tasks')
    payload = json.loads(job['payload_snapshot'])
    assert payload['altText'] == '案件〈115000157〉訂金 NT$12,000已確認入帳，謝謝您。'
    assert payload['contents']['footer']['contents'][0]['action']['label'] == '查看繳費狀態'
    payment = application(db).query_customer(CASE, USER)
    assert str(payment.received_on) == '2026-10-20'
    assert application(db).run_once() == 0
    db.execute("UPDATE client_finance_outbox SET status='delivered'");db.commit()
    assert application(db).run_once() == 0
    assert len(rows(db, 'line_delivery_tasks')) == 1
    orders_intent = next(row for row in rows(db,'client_finance_outbox') if row['intent_type']=='orders_deposit_reconciled')
    assert orders_intent['status'] == 'delivered'


def test_finance_rollback_leaves_neither_notification_intent_nor_success_job(db):
    settle(db, commit=False)
    db.rollback()
    assert not rows(db, 'client_finance_outbox') and not rows(db, 'client_deposit_settlement_projection')
    assert application(db).run_once() == 0
    assert not application(db).query_customer(CASE, USER).settled


def test_historical_settlement_is_visible_without_automatic_backfill(db):
    settle(db)
    event = json.loads(rows(db,'client_finance_outbox')[0]['payload_snapshot'])
    del event['line_deposit_notification']
    db.execute('UPDATE client_finance_outbox SET payload_snapshot=?',(json.dumps(event),));db.commit()
    assert application(db).query_customer(CASE,USER).settled
    assert application(db).run_once()==0
    assert not rows(db,'line_delivery_tasks')
    assert Uow(db).deposit_notifications.followups().items == ()


def test_queue_failure_rolls_back_notification_and_can_retry_same_settlement(db,monkeypatch):
    settle(db)
    original = MySqlLineDeliveryTaskRepository.enqueue
    def fail_after_enqueue(self, request):
        original(self,request)
        raise RuntimeError('synthetic failure before commit')
    monkeypatch.setattr(MySqlLineDeliveryTaskRepository,'enqueue',fail_after_enqueue)
    with pytest.raises(RuntimeError,match='before commit'): application(db).run_once()
    assert not rows(db,'line_delivery_tasks')
    assert application(db).query_customer(CASE,USER).settled
    monkeypatch.setattr(MySqlLineDeliveryTaskRepository,'enqueue',original)
    assert application(db).run_once()==1


def test_noncanonical_case_without_unique_imported_account_stays_pending(db):
    db.execute("UPDATE orders SET case_no='CASE-NONCANONICAL'")
    db.execute("UPDATE order_contract_flow_events SET case_no='CASE-NONCANONICAL'")
    db.execute("UPDATE client_obligations SET case_no='CASE-NONCANONICAL'");db.commit()
    payment=application(db).query_customer('CASE-NONCANONICAL',USER)
    assert payment.virtual_account is None
    items=Uow(db).deposit_notifications.followups().items
    assert len(items)==1 and not application(db).ready(items[0].payment)
    assert not rows(db,'line_delivery_tasks')


def test_unbound_success_is_staff_todo_not_fake_sent_then_binding_can_resume(db):
    settle(db)
    db.execute("UPDATE line_identity_role_bindings SET binding_status='suspended'");db.commit()
    assert application(db).run_once() == 0
    assert not rows(db, 'line_delivery_tasks')
    page = Uow(db).deposit_notifications.followups()
    items, total = page.items, page.total
    assert len(items) == 1 and items[0].payment.settled and not items[0].line_bound
    assert total == 1
    db.execute("UPDATE line_identity_role_bindings SET binding_status='bound'")
    db.commit()
    application(db).run_once()
    assert len(rows(db,'line_delivery_tasks')) == 1


@pytest.mark.parametrize('change', ['settled','rebind','version','cancelled','reversed','unsigned'])
def test_provider_guard_cancels_outdated_tasks_and_never_calls_provider(db, change):
    if change == 'reversed':
        settle(db);application(db).run_once()
        db.execute("UPDATE client_deposit_settlement_projection SET settlement_state='unsettled'")
    else:
        application(db).send_reminder(CASE,2,IdempotencyKey('one'),ACTOR)
        if change == 'settled': settle(db)
        if change == 'rebind': db.execute("UPDATE clients SET line_user_id='U-new'");db.execute("UPDATE line_identity_role_bindings SET line_user_id='U-new'")
        if change == 'version': db.execute('UPDATE client_obligations SET projection_version=3')
        if change == 'cancelled': db.execute("UPDATE orders SET status='訂單取消'")
        if change == 'unsigned': db.execute('DELETE FROM order_contract_flow_events')
    db.execute("UPDATE line_delivery_tasks SET processing_status='processing',lease_owner='test',lease_acquired_at_utc=?,lease_expires_at_utc=?", (NOW.isoformat(' '), (NOW+timedelta(seconds=60)).isoformat(' ')))
    db.commit()
    task = Uow(db).delivery_tasks.get(LineDeliveryTaskId(1))
    worker = LineDeliveryWorker(lambda: Uow(db),SimpleNamespace(send=lambda _: pytest.fail('stale job reached provider')),'test',lambda:NOW,batch_size=1)
    worker._claim=lambda:(task,)
    assert worker.run_once() == 1
    assert rows(db,'line_delivery_tasks')[0]['processing_status'] == 'cancelled'


def test_customer_query_checks_current_binding_and_cannot_mark_paid(db):
    with pytest.raises(DepositPaymentForbidden): application(db).query_customer(CASE, 'U-other')
    payment = application(db).query_customer(CASE, USER)
    assert not payment.settled and payment.virtual_account
    db.execute("UPDATE line_identity_role_bindings SET binding_status='suspended'");db.commit()
    with pytest.raises(DepositPaymentForbidden): application(db).query_customer(CASE, USER)
    assert not rows(db,'client_ledger_entries')


def test_assistance_button_uses_same_ticket_and_chat_ack_no_group_or_payment_effect(db):
    commands=[]
    uow=Uow(db)
    uow.customer_service=SimpleNamespace(create_or_append=lambda command: commands.append(command) or SimpleNamespace(ticket_id=55))
    event=SimpleNamespace(event_id=SimpleNamespace(value='synthetic-click'),source=SimpleNamespace(user_id=LineUserId(USER)),occurred_at=NOW)
    assert handle_deposit_assistance('deposit-assistance:'+CASE,event,uow)
    uow.commit()
    assert commands[0].case_no == CASE
    assert json.loads(rows(db,'line_delivery_tasks')[0]['payload_snapshot'])['text'] == ASSISTANCE_ACK
    db.execute("INSERT INTO customer_service_tickets VALUES (55,?,'other','waiting',1,?)", (USER,CASE))
    db.execute('INSERT INTO customer_service_ticket_events VALUES (55,?)',(commands[0].event_key,));db.commit()
    ticket=MySqlCustomerServiceRepository(Connection(db)).active_matching_assistance(USER)
    assert ticket.ticket_id == 55 and ticket.case_no == CASE
    from subsystems.line.matching_postback_application import LineMatchingPostbackApplication
    from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
    uow.matching_schedule_confirmations=SimpleNamespace(confirm_line_rejection_reason=lambda *args:False)
    uow.customer_service.active_matching_assistance=lambda user:ticket
    consumer=LineMatchingPostbackApplication(MatchingNotificationApplication(lambda:uow,lambda:NOW,availability_validator=lambda _:None))
    assert consumer.handle_message(SimpleNamespace(event=event),uow,LineUserId(USER),'已付款')
    assert commands[-1].case_no==CASE and commands[-1].message=='已付款'
    assert not rows(db,'client_ledger_entries')
    event.source.user_id=LineUserId('U-other')
    assert handle_deposit_assistance('deposit-assistance:'+CASE,event,uow)
    assert len(commands) == 2 and not rows(db,'client_ledger_entries')


def test_verified_customer_route_and_staff_capability_guards(db, monkeypatch):
    from api.routes import line_deposit_payment as route
    capabilities=[]
    monkeypatch.setattr(route,'get_deposit_notifications',lambda:application(db))
    monkeypatch.setattr(route,'get_liff_token_verifier',lambda:SimpleNamespace(verify=lambda token:SimpleNamespace(line_user_id=USER if token=='owner' else 'U-other')))
    monkeypatch.setattr(route,'_mobile_admin_context',lambda token,cap:(capabilities.append(cap) or None,ACTOR))
    monkeypatch.setattr(route,'open_line_unit_of_work',lambda:Uow(db))
    api=FastAPI();api.include_router(route.router)
    client=TestClient(api)
    path='/api/v1/line/deposit-payment/query'
    result=client.post(path,json={'line_id_token':'owner','case_no':CASE})
    assert result.status_code == 200 and result.json()['data']['status']=='unpaid'
    assert result.headers['cache-control']=='no-store'
    assert client.post(path,json={'line_id_token':'other','case_no':CASE}).status_code==403
    assert client.post(path,json={'line_id_token':'owner','case_no':CASE,'line_user_id':USER}).status_code==422
    staff='/api/v1/line/mobile-admin/deposit-payments'
    result=client.post(staff,json={'line_id_token':'owner','page':1})
    assert result.status_code==200 and 'virtual_account' not in result.json()['data']['items'][0]
    assert result.json()['data']['total'] == 1
    assert client.post(staff+'/remind',json={'line_id_token':'owner','case_no':CASE,'expected_version':2,'idempotency_key':'one'}).status_code==200
    assert capabilities==[LineCapability.TASK_READ,LineCapability.TASK_SEND]
    db.execute('DELETE FROM order_contract_flow_events')
    db.commit()
    unsigned=client.post(staff,json={'line_id_token':'owner','page':1}).json()['data']
    assert unsigned['items']==[] and unsigned['total']==0
    response=client.post(staff+'/remind',json={'line_id_token':'owner','case_no':CASE,'expected_version':2,'idempotency_key':'unsigned'})
    assert response.status_code==409
    assert 'deposit_contract_not_completed' in response.text and '雙方簽約' in response.text
    assert len(rows(db,'line_delivery_tasks'))==1


@pytest.mark.parametrize('pending_count', [26, 101])
def test_staff_todo_total_counts_eligible_payments_before_pagination(db, monkeypatch, pending_count):
    from api.routes import line_deposit_payment as route

    # A historical settlement and ambiguous obligations are not current todos.
    settle(db)
    db.execute("UPDATE client_finance_outbox SET payload_snapshot='{}'")
    db.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('000-UNSIGNED',1,'洽談中')")
    db.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,status,projection_version,amount_due_ntd,due_date) "
               "VALUES ('unsigned-deposit','000-UNSIGNED','deposit','receivable_from_client','open',1,1000,'2026-11-01')")
    db.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('000-AMBIGUOUS',1,'洽談中')")
    complete_contract(db, '000-AMBIGUOUS')
    for index in range(2):
        db.execute(
            "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,status,projection_version,amount_due_ntd,due_date) VALUES (?, '000-AMBIGUOUS', 'deposit', "
            "'receivable_from_client','open',1,1000,'2026-11-01')", (f'ambiguous-{index}',),
        )
    cases = [f'TODO-{index:04d}' for index in range(pending_count)]
    for case_no in cases:
        db.execute("INSERT INTO orders(case_no,client_id,status) VALUES (?,1,'洽談中')", (case_no,))
        complete_contract(db, case_no)
        db.execute(
            "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,status,projection_version,amount_due_ntd,due_date) VALUES (?,?,'deposit','receivable_from_client',"
            "'open',1,1000,'2026-11-01')", ('deposit-' + case_no, case_no),
        )
    db.commit()
    before = {table: rows(db, table) for table in (
        'client_obligations', 'client_finance_outbox', 'line_delivery_tasks',
    )}
    capabilities = []
    monkeypatch.setattr(route, 'get_deposit_notifications', lambda: application(db))
    monkeypatch.setattr(route, '_mobile_admin_context', lambda token, cap: capabilities.append(cap))
    monkeypatch.setattr(route, 'open_line_unit_of_work', lambda: Uow(db))
    api = FastAPI()
    api.include_router(route.router)
    client = TestClient(api)

    def query(page):
        response = client.post('/api/v1/line/mobile-admin/deposit-payments', json={
            'line_id_token': 'synthetic-staff', 'page': page, 'page_size': 25,
        })
        assert response.status_code == 200
        data = response.json()['data']
        assert data['total'] == pending_count
        assert data['page'] == page
        return data

    seen = []
    last_page = (pending_count + 24) // 25
    for page in range(1, last_page + 1):
        data = query(page)
        expected = cases[(page - 1) * 25:page * 25]
        assert [item['case_no'] for item in data['items']] == expected
        assert data['has_next'] == (page < last_page)
        seen.extend(expected)
    assert seen == cases
    assert len(query(1)['items']) == 25
    beyond = query(last_page + 1)
    assert beyond['items'] == [] and not beyond['has_next']
    assert set(capabilities) == {LineCapability.TASK_READ}
    assert {table: rows(db, table) for table in before} == before


def test_settlement_filters_keep_the_same_pending_total_and_completed_notice_leaves(db):
    db.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('PUBLIC-UNPAID',1,'洽談中')")
    complete_contract(db, 'PUBLIC-UNPAID')
    db.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,status,projection_version,amount_due_ntd,due_date) VALUES ('deposit-unpaid','PUBLIC-UNPAID','deposit',"
               "'receivable_from_client','open',1,1000,'2026-11-01')")
    db.commit()
    settle(db)
    application(db).run_once()  # Memory-only queue; no provider exists in this test.
    repository = Uow(db).deposit_notifications
    unpaid = repository.followups(settled=False)
    settled = repository.followups(settled=True)
    assert unpaid.total == settled.total == 2
    assert unpaid.unpaid_total == settled.unpaid_total == 1
    assert unpaid.settled_total == settled.settled_total == 1
    assert unpaid.page_total == settled.page_total == 1
    assert not unpaid.items[0].payment.settled and settled.items[0].payment.settled
    db.execute("UPDATE line_delivery_tasks SET processing_status='sent'")
    completed = repository.followups(settled=True)
    assert completed.items == () and completed.page_total == completed.settled_total == 0
    assert completed.total == completed.unpaid_total == 1


def test_same_case_focus_filters_before_paging_and_exits_after_notice_sent(db):
    db.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('PUBLIC-OTHER',1,'洽談中')")
    complete_contract(db, 'PUBLIC-OTHER')
    db.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,status,projection_version,amount_due_ntd,due_date) VALUES ('deposit-other','PUBLIC-OTHER','deposit',"
               "'receivable_from_client','open',1,1000,'2026-11-01')")
    db.commit();settle(db);application(db).run_once()
    repository=Uow(db).deposit_notifications
    selected=repository.followups(case_no=CASE,settled=True,page_size=1)
    assert selected.page_total==selected.total==1 and selected.items[0].payment.case_no==CASE
    assert repository.followups(case_no=CASE,settled=False).items==()
    assert repository.followups(case_no=CASE,settled=True,page=2,page_size=1).items==()
    before=rows(db,'client_obligations')
    assert repository.followups(case_no='PUBLIC-OTHER',settled=False).items[0].payment.case_no=='PUBLIC-OTHER'
    assert rows(db,'client_obligations')==before
    db.execute("UPDATE line_delivery_tasks SET processing_status='sent'")
    assert repository.followups(case_no=CASE,settled=True).items==()


def test_paid_query_uses_committed_amount_while_partial_payment_uses_remaining(db):
    db.execute("UPDATE client_obligations SET amount_due_ntd=7000")
    partial=MySqlDepositPaymentQueryRepository(Connection(db)).get(CASE)
    assert partial.amount_ntd==7000 and not partial.settled
    settle(db)
    paid=MySqlDepositPaymentQueryRepository(Connection(db)).get(CASE)
    assert paid.amount_ntd==12000 and paid.settled
    assert db.execute('SELECT amount_due_ntd FROM client_obligations').fetchone()[0]==0


@pytest.mark.parametrize('field,label', [('due_date','繳費到期日'),('virtual_account','案件虛擬帳號'),('bank_code','銀行代碼'),('liff','LINE 繳費頁面設定')])
def test_reminder_blocker_names_exact_missing_item_without_enqueuing(db,field,label):
    from dataclasses import replace
    from datetime import date
    from api.routes.line_deposit_payment import deposit_reminder_blocker
    payment=MySqlDepositPaymentQueryRepository(Connection(db)).get(CASE)
    payment=replace(payment,due_date=date(2026,11,1),virtual_account='12345678901234')
    if field in ('due_date','virtual_account'):
        payment=replace(payment,**{field:None})
    app=DepositNotificationApplication(lambda:Uow(db),lambda:NOW,liff_id='' if field=='liff' else 'synthetic-liff',bank_code='' if field=='bank_code' else '807')
    before=db.execute('SELECT COUNT(*) FROM line_delivery_tasks').fetchone()[0]
    assert app.missing_reminder_fields(payment)==(field,)
    assert app.ready(payment) is False
    reason=deposit_reminder_blocker(app,payment,False)
    assert label in reason and '客戶尚未綁定 LINE' in reason and '請核對案件帳務及系統設定' in reason
    for other in ('繳費到期日','案件虛擬帳號','銀行代碼','LINE 繳費頁面設定'):
        if other!=label:assert other not in reason
    assert db.execute('SELECT COUNT(*) FROM line_delivery_tasks').fetchone()[0]==before

"""Private initial reminders, original-send timing, and reply-driven manual handoff."""
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import json
import pytest

from domains.line.configuration import LineConfigurationKind
from domains.line.delivery import LineDeliveryStatus, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineUserId
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
from subsystems.client_finance.payment_reminder_query import ClientPaymentReminderFacts
from subsystems.line.deposit_notifications import DepositNotificationApplication
from subsystems.line.message_configuration import LineMessageConfigurationError,validate_message_schedules
from subsystems.line.payment_overdue_reminders import ReminderRecipient
from subsystems.line.payment_reminder_notifications import (
    INITIAL,FOLLOWUP,OriginalPaymentReminder,PaymentReminderNotificationWorker,payment_reminder_delivery_is_current,
)
from subsystems.line.payment_reminder_schedule import PaymentReminderSchedule,followup_at,parse_schedule
from shared_kernel.identities import IdempotencyKey,IdempotencyReceipt
from shared_kernel.fingerprints import fingerprint_payload

NOW=datetime(2026,11,5,1,tzinfo=timezone.utc)  # Taipei 09:00.
USER='U'+'1'*32


class Unit:
    def __init__(self,stage='second',amount=24000):
        self.now=NOW
        self.facts=ClientPaymentReminderFacts(OverdueClientPayment('CASE-1',stage,'CASE-1:'+stage,3,7,date(2026,11,5),amount),date(2026,11,5),True,'服務中')
        self.schedule=PaymentReminderSchedule()
        self.recipient_value=ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId(USER)),0)
        self.rows=[];self.events=[];self.commits=0;self.reply=False;self._committed=False
        self.handoffs={}
        self.receipts=SimpleNamespace(get=lambda key,**_:self.handoffs.get(key.value),append=lambda receipt:self.handoffs.setdefault(receipt.key.value,receipt))
        self.payment_reminder_notifications=SimpleNamespace(candidates=lambda *_: (self.facts,),payment=lambda *_,**__:self.facts,
            recipient=lambda *_,**__:self.recipient_value,original=self.original,has_followup=lambda _:any(row.request.source_aggregate_type==FOLLOWUP for row in self.rows),
            pending=lambda _:any(row.status in ('pending','processing','retryable_failed') for row in self.rows),replied=lambda *_:self.reply)
        self.configurations=SimpleNamespace(get=lambda kind:SimpleNamespace(revision=SimpleNamespace(value=1),definition_json=json.dumps(
            {'payment_reminders':asdict(self.schedule)} if kind is LineConfigurationKind.MESSAGE_SCHEDULES else {'templates':[]})))
        self.delivery_tasks=SimpleNamespace(enqueue=self.enqueue,cancel=self.cancel,exists_for_key=lambda key:any(row.request.idempotency_key==key for row in self.rows))
        self.audit=SimpleNamespace(append=self.events.append)
        self.deposit_payments=SimpleNamespace(get=lambda *_,**__:SimpleNamespace(case_no='CASE-1',obligation_identity='CASE-1:deposit',obligation_version=3,
            amount_ntd=self.facts.payment.remaining_amount_ntd,due_date=self.facts.payment.due_date,virtual_account='12345678901234',settlement_identity=None,settled=False))
    def __enter__(self):
        self._committed=False
        return self
    def __exit__(self,*_):return False
    def commit(self):self._committed=True;self.commits+=1
    def enqueue(self,request):
        row=SimpleNamespace(task_id=SimpleNamespace(value=len(self.rows)+1),request=request,status='pending',sent_at=None)
        self.rows.append(row)
        return SimpleNamespace(task_id=row.task_id,status=LineDeliveryStatus.PENDING)
    def cancel(self,command):
        self.rows[command.task_id.value-1].status='cancelled'
    def original(self,*_,**__):
        initial=next((row for row in self.rows if row.request.source_aggregate_type==INITIAL),None)
        return OriginalPaymentReminder(initial.task_id.value,initial.status,initial.sent_at,initial.request.recipient.identity.value,
                                       initial.request.recipient.recipient_type is LineRecipientType.GROUP) if initial else None
    def worker(self):
        deposit=DepositNotificationApplication(lambda:self,lambda:self.now,liff_id='synthetic-liff',bank_code='807')
        return PaymentReminderNotificationWorker(lambda:self,lambda:self.now,deposit)
    def sent(self,at=NOW):
        self.rows[0].status='sent';self.rows[0].sent_at=at


@pytest.mark.parametrize('stage',['deposit','second'])
def test_each_stage_auto_queues_only_one_private_reminder_without_provider(stage):
    unit=Unit(stage)
    assert unit.worker().run_once()==1
    assert unit.worker().run_once()==0
    assert len(unit.rows)==1 and unit.commits==1
    request=unit.rows[0].request
    assert request.recipient.recipient_type is LineRecipientType.USER and request.recipient.identity.value==USER
    assert request.source_aggregate_type==INITIAL
    assert '24,000' in request.payload_json
    assert payment_reminder_delivery_is_current(unit,unit.rows[0],unit.now)


@pytest.mark.parametrize('amount',[0, 24000])
def test_payment_worker_never_sends_first_day_reminder(amount):
    unit=Unit('first',amount)
    assert unit.worker().run_once()==0
    assert not unit.rows


def test_zero_second_stage_does_not_notify():
    unit=Unit('second',0)
    assert unit.worker().run_once()==0
    assert not unit.rows


def test_initial_waits_for_configured_time_and_does_not_backfill_past_days():
    stage='second'
    unit=Unit(stage);unit.schedule=replace(unit.schedule,second_time='10:00')
    assert unit.worker().run_once()==0
    unit.now+=timedelta(hours=1)
    assert unit.worker().run_once()==1
    other=Unit(stage);other.now+=timedelta(days=1)
    assert other.worker().run_once()==0


def test_fixed_time_deposit_is_queued_for_next_slot_without_repeated_projection():
    unit=Unit('deposit');unit.schedule=replace(unit.schedule,deposit_mode='daily',deposit_time='08:00')
    assert unit.worker().run_once()==1
    assert unit.rows[0].request.scheduled_at.astimezone(timezone.utc)==datetime(2026,11,6,0,tzinfo=timezone.utc)
    assert unit.worker().run_once()==0


@pytest.mark.parametrize('stage',['deposit','second'])
def test_overdue_followup_is_once_per_stage_after_original_success_and_24_hours(stage):
    unit=Unit(stage);worker=unit.worker();assert worker.run_once()==1
    unit.sent();unit.now=NOW+timedelta(days=1,minutes=59)
    assert worker.run_once()==0  # Still before the configured 10:00 slot.
    unit.now+=timedelta(minutes=1)
    assert worker.run_once()==1
    assert len(unit.rows)==2 and unit.rows[1].request.source_aggregate_type==FOLLOWUP
    assert payment_reminder_delivery_is_current(unit,unit.rows[1],unit.now)
    unit.rows[1].status='sent';unit.now+=timedelta(days=10)
    assert worker.run_once()==0 and len(unit.rows)==2


def test_counting_starts_at_actual_success_not_queue_time():
    unit=Unit();worker=unit.worker();worker.run_once()
    unit.sent(NOW+timedelta(hours=2))
    unit.now=NOW+timedelta(days=1,hours=1)
    assert worker.run_once()==0
    unit.now=NOW+timedelta(days=2,hours=1)
    assert worker.run_once()==1


def test_failed_or_unsent_original_never_starts_the_followup_clock():
    unit=Unit();worker=unit.worker();worker.run_once();unit.rows[0].status='failed'
    unit.now+=timedelta(days=3)
    assert worker.run_once()==0 and len(unit.rows)==1


def test_reply_after_queue_cancels_followup_before_provider_and_retains_finance():
    unit=Unit();worker=unit.worker();worker.run_once();unit.sent();unit.now+=timedelta(days=1,hours=1)
    assert worker.run_once()==1
    before=unit.facts
    unit.reply=True
    assert not payment_reminder_delivery_is_current(unit,unit.rows[1],unit.now)
    assert unit.rows[1].status=='cancelled' and unit.facts==before
    unit.now+=timedelta(days=1)
    assert worker.run_once()==0


def test_reply_before_scan_leaves_unpaid_item_for_manual_handling():
    unit=Unit();worker=unit.worker();worker.run_once();unit.sent();unit.reply=True;unit.now+=timedelta(days=1,hours=1)
    assert worker.run_once()==0 and unit.facts.payment.remaining_amount_ntd==24000
    unit.reply=False  # Inbox lifecycle cannot restart an already recorded handoff.
    assert unit.worker().run_once()==0


def test_another_command_receipt_cannot_forge_a_customer_reply_handoff():
    unit=Unit();unit.worker().run_once();unit.sent()
    key=IdempotencyKey('payment-reminder-replied:1')
    unit.handoffs[key.value]=IdempotencyReceipt(key,fingerprint_payload({'unrelated_command':1}),'unrelated_result')
    with pytest.raises(RuntimeError,match='payment_reminder_handoff_receipt_conflict'):
        unit.worker().run_once()
    assert len(unit.rows)==1


@pytest.mark.parametrize('change',[
    {'contract_completed':False},{'payment':replace(Unit().facts.payment,remaining_amount_ntd=0)},
    {'payment':replace(Unit().facts.payment,due_date=date(2026,11,20))},
])
def test_updated_facts_stop_queued_followup(change):
    unit=Unit();worker=unit.worker();worker.run_once();unit.sent();unit.now+=timedelta(days=1,hours=1);worker.run_once()
    unit.facts=replace(unit.facts,**change)
    assert not payment_reminder_delivery_is_current(unit,unit.rows[1],unit.now)


def test_rebinding_never_sends_to_old_customer():
    unit=Unit();unit.worker().run_once()
    unit.recipient_value=ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId('U'+'2'*32)),0)
    assert not payment_reminder_delivery_is_current(unit,unit.rows[0],unit.now)


def test_schedule_edits_do_not_rewrite_or_cancel_already_committed_work():
    unit=Unit();worker=unit.worker();worker.run_once()
    unit.schedule=replace(unit.schedule,second_time='23:00')
    assert payment_reminder_delivery_is_current(unit,unit.rows[0],unit.now)
    unit.sent();unit.now+=timedelta(days=1,hours=1);worker.run_once()
    unit.schedule=replace(unit.schedule,overdue_time='23:00')
    assert payment_reminder_delivery_is_current(unit,unit.rows[1],unit.now)


def test_first_overdue_follows_group_opening_only_in_customer_private_chat():
    unit=Unit('first')
    group='C_ORIGINAL'
    original=OriginalPaymentReminder(1,'sent',NOW,group,sent_to_group=True)
    unit.payment_reminder_notifications.original=lambda *_,**__:original
    unit.now=NOW+timedelta(days=1,hours=1)
    assert unit.worker().run_once()==1
    request=unit.rows[0].request
    assert request.source_aggregate_type==FOLLOWUP
    assert request.recipient.recipient_type is LineRecipientType.USER
    assert request.recipient.identity.value==USER
    unit.recipient_value=ReminderRecipient(LineRecipient(LineRecipientType.GROUP,LineGroupId(group)),0)
    assert not payment_reminder_delivery_is_current(unit,unit.rows[0],unit.now)


def test_first_overdue_respects_opening_payment_handoff_record():
    from subsystems.line.payment_reminder_notifications import record_manual_handoff

    unit=Unit('first')
    original=OriginalPaymentReminder(1,'sent',NOW,'C_ORIGINAL',sent_to_group=True)
    unit.payment_reminder_notifications.original=lambda *_,**__:original
    unit.now=NOW+timedelta(days=1,hours=1)
    record_manual_handoff(unit,original.task_id)
    assert unit.worker().run_once()==0
    assert not unit.rows


def test_deposit_waits_for_signed_contract_and_missing_customer_stays_unqueued():
    unit=Unit('deposit');unit.facts=replace(unit.facts,contract_completed=False)
    assert unit.worker().run_once()==0
    unit.facts=replace(unit.facts,contract_completed=True);unit.recipient_value=None
    assert unit.worker().run_once()==0


@pytest.mark.parametrize('value',['24:00','9:00','10:60','',True,'0９:00'])
def test_invalid_schedule_cannot_be_stored_or_executed(value):
    definition={**asdict(PaymentReminderSchedule()),'overdue_time':value}
    with pytest.raises(LineMessageConfigurationError):parse_schedule(definition)
    with pytest.raises(LineMessageConfigurationError):validate_message_schedules({'schedules':[],'payment_reminders':definition},{'templates':[]})


def test_followup_uses_taipei_date_and_next_slot_after_full_24_hours():
    sent=datetime(2026,11,5,6,tzinfo=timezone.utc)  # Taipei 14:00.
    assert followup_at(date(2026,11,5),sent,PaymentReminderSchedule()).isoformat()=='2026-11-07T10:00:00+08:00'


@pytest.mark.parametrize('stage',['deposit','second'])
@pytest.mark.parametrize('continuation_day',[None,date(2026,11,6)])
def test_historical_old_or_unproven_cutoff_never_queues_automatic_initial(stage,continuation_day):
    from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts
    unit=Unit(stage)
    unit.facts=replace(unit.facts,contract_completed=False,
        notification_continuation=OrderNotificationContinuationFacts(True,True,continuation_day))
    assert unit.worker().run_once()==0
    assert unit.rows==[] and unit.commits==0


@pytest.mark.parametrize('formally_arranged',[False,True])
def test_historical_continuation_uses_arrangement_and_keeps_today_payment_rules(formally_arranged):
    from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts
    unit=Unit('second')
    unit.facts=replace(unit.facts,contract_completed=False,
        notification_continuation=OrderNotificationContinuationFacts(True,formally_arranged,date(2026,11,5)))
    assert unit.worker().run_once()==int(formally_arranged)
    if formally_arranged:
        assert payment_reminder_delivery_is_current(unit,unit.rows[0],unit.now)
        assert not unit.facts.contract_completed
        unit.sent();unit.now+=timedelta(days=1,hours=1)
        assert unit.worker().run_once()==1
        assert payment_reminder_delivery_is_current(unit,unit.rows[1],unit.now)


@pytest.mark.parametrize('initial_queued',[False,True])
def test_new_historical_facts_cancel_preexisting_automatic_work_at_provider(initial_queued):
    from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts
    unit=Unit('deposit');unit.worker().run_once()
    if not initial_queued:
        unit.sent();unit.now+=timedelta(days=1,hours=1);unit.worker().run_once()
    task=unit.rows[-1]
    unit.facts=replace(unit.facts,
        notification_continuation=OrderNotificationContinuationFacts(True,True,date(2026,11,6)))
    assert not payment_reminder_delivery_is_current(unit,task,unit.now)
    assert task.status=='cancelled'
    unit.now+=timedelta(days=1)
    assert unit.worker().run_once()==0



@pytest.mark.parametrize('arranged,cutoff,key,expected',[
    (False,None,'deposit-reminder:human',False),
    (True,None,'deposit-reminder:human',True),
    (True,None,'legacy-deposit-automatic',False),
    (True,date(2026,11,6),'legacy-deposit-automatic',False),
    (True,date(2026,11,6),'deposit-reminder:human',True),
    (True,date(2026,11,5),'legacy-deposit-automatic',True),
])
def test_independent_deposit_provider_requires_continuation_and_explicit_old_debt_choice(arranged,cutoff,key,expected):
    from unittest.mock import Mock
    from subsystems.client_finance.deposit_payment_query import DepositPayment
    from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts
    from subsystems.line.deposit_notifications import REMINDER,payment_source,deposit_delivery_is_current
    from shared_kernel.identities import CorrelationId
    payment=DepositPayment('H','H:deposit',1,100,date(2026,11,5),'12345678901234',None,None,
        OrderNotificationContinuationFacts(True,arranged,cutoff))
    recipient=LineRecipient(LineRecipientType.USER,LineUserId(USER))
    task=SimpleNamespace(task_id=SimpleNamespace(value=9),request=SimpleNamespace(
        source_aggregate_type=REMINDER,source_aggregate_identity=payment_source(payment),
        recipient=recipient,idempotency_key=IdempotencyKey(key),correlation_id=CorrelationId('deposit-source')))
    unit=SimpleNamespace(deposit_payments=SimpleNamespace(get=Mock(return_value=payment)),
        deposit_notifications=SimpleNamespace(customer_line_user_id=Mock(return_value=USER),contract_completed=Mock(return_value=False)),
        delivery_tasks=SimpleNamespace(cancel=Mock()),commit=Mock())
    assert deposit_delivery_is_current(unit,task,NOW) is expected
    assert unit.delivery_tasks.cancel.call_count==int(not expected)


def test_first_greeting_does_not_include_old_historical_payment(monkeypatch):
    from infrastructure.mysql import service_start_day_repository as repository
    from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts
    unit=Unit('first')
    unit.facts=replace(unit.facts,
        notification_continuation=OrderNotificationContinuationFacts(True,True,date(2026,11,6)))
    query=SimpleNamespace(for_case=lambda case:(unit.facts,),get=lambda *args,**kwargs:unit.facts)
    monkeypatch.setattr(repository,'MySqlClientPaymentReminderQueryRepository',lambda connection:query)
    current=repository.MySqlServiceStartDayRepository(None)
    assert current.first_payment('CASE-1') is None
    unit.facts=replace(unit.facts,
        notification_continuation=OrderNotificationContinuationFacts(True,True,date(2026,11,5)))
    assert current.first_payment('CASE-1')==unit.facts.payment


def test_customer_binding_reminders_count_and_items_share_owner_eligibility():
    from unittest.mock import Mock
    from domains.line.identity_binding import LineBindingSubjectType
    from infrastructure.mysql.line_identity_management_repository import MySqlLineIdentityManagementRepository
    from infrastructure.mysql.order_notification_continuation_query_repository import notification_continuation_eligible_sql
    from subsystems.line.identity_management_contracts import LineIdentityCandidateQuery
    cursor=Mock();cursor.__enter__=Mock(return_value=cursor);cursor.__exit__=Mock(return_value=False)
    cursor.fetchone.return_value={'total':1}
    cursor.fetchall.return_value=({'subject_reference':1,'subject_name':'case client','phone':None,'case_no':'H'},)
    repo=MySqlLineIdentityManagementRepository(SimpleNamespace(cursor=lambda:cursor))
    result=repo.binding_reminders(LineIdentityCandidateQuery(LineBindingSubjectType.CUSTOMER,page=2,page_size=5))
    count,items=cursor.execute.call_args_list
    count_where=count.args[0].split(' WHERE ',1)[1]
    items_where=items.args[0].split(' WHERE ',1)[1].rsplit(' ORDER BY ',1)[0]
    assert count_where==items_where
    assert notification_continuation_eligible_sql('o') in count_where
    assert count.args[1]==items.args[1][:-2]
    assert items.args[1][-2:]==(5,5)
    assert result.total==1 and result.items[0].case_no=='H'

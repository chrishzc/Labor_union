"""Manual-only overdue acceptance: stage isolation, fresh facts and safe replay."""
from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from shared_kernel.identities import ActorContext
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
from subsystems.line.payment_overdue_reminders import (
    PaymentOverdueReminderApplication,PaymentOverdueReminderConflict,ReminderRecipient,payment_reference,reminder_text,
)

NOW=datetime(2032,5,10,16,tzinfo=timezone.utc)  # Taipei has entered May 11.
PAYMENT=OverdueClientPayment('CASE-1','deposit','case-1:deposit',3,7,date(2032,5,10),18000)


class Unit:
    def __init__(self):
        self.payment_overdue_reminders=SimpleNamespace(list=Mock(return_value=((),0)),payment=Mock(return_value=PAYMENT),
            existing=Mock(return_value=None),recipient=Mock(return_value=ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId('U'+'1'*32)),0)))
        self.delivery_tasks=SimpleNamespace(enqueue=Mock(return_value=SimpleNamespace(task_id=SimpleNamespace(value=1),status=SimpleNamespace(value='pending'))))
        self.audit=SimpleNamespace(append=Mock());self.commit=Mock()
    def __enter__(self):return self
    def __exit__(self,*args):return False


def test_query_uses_taipei_next_day_without_enqueue_or_commit():
    unit=Unit();app=PaymentOverdueReminderApplication(lambda:unit,lambda:NOW)
    assert app.list()==((),0)
    unit.payment_overdue_reminders.list.assert_called_once_with(date(2032,5,11),1,25)
    unit.delivery_tasks.enqueue.assert_not_called();unit.commit.assert_not_called()


@pytest.mark.parametrize('change',[
    {'case_no':'CASE-2'},{'payment_stage':'first'},{'projection_version':4},{'obligation_event_id':8},
    {'due_date':date(2032,5,12)},{'remaining_amount_ntd':19000},
])
def test_changed_selected_stage_snapshot_conflicts_without_task(change):
    unit=Unit();unit.payment_overdue_reminders.payment.return_value=replace(PAYMENT,**change)
    with pytest.raises(PaymentOverdueReminderConflict,match='payment_overdue_changed'):
        PaymentOverdueReminderApplication(lambda:unit,lambda:NOW).send(PAYMENT,'key',ActorContext('union'))
    unit.delivery_tasks.enqueue.assert_not_called();unit.commit.assert_not_called()


@pytest.mark.parametrize('current',[None,replace(PAYMENT,remaining_amount_ntd=0)])
def test_cleared_or_missing_payment_never_enqueues(current):
    unit=Unit();unit.payment_overdue_reminders.payment.return_value=current
    with pytest.raises(PaymentOverdueReminderConflict):
        PaymentOverdueReminderApplication(lambda:unit,lambda:NOW).send(PAYMENT,'key',ActorContext('union'))
    unit.delivery_tasks.enqueue.assert_not_called()


def test_due_today_is_not_overdue():
    unit=Unit()
    with pytest.raises(PaymentOverdueReminderConflict):
        PaymentOverdueReminderApplication(lambda:unit,lambda:datetime(2032,5,10,15,59,tzinfo=timezone.utc)).send(PAYMENT,'key',ActorContext('union'))
    unit.delivery_tasks.enqueue.assert_not_called()


def test_missing_recipient_retains_payment_without_task():
    unit=Unit();unit.payment_overdue_reminders.recipient.return_value=None
    with pytest.raises(PaymentOverdueReminderConflict,match='recipient_unavailable'):
        PaymentOverdueReminderApplication(lambda:unit,lambda:NOW).send(PAYMENT,'key',ActorContext('union'))
    unit.delivery_tasks.enqueue.assert_not_called()


def test_send_commits_task_and_human_audit_without_provider():
    unit=Unit()
    assert PaymentOverdueReminderApplication(lambda:unit,lambda:NOW).send(PAYMENT,'key',ActorContext('union'))==(1,'pending')
    task=unit.delivery_tasks.enqueue.call_args.args[0]
    assert task.source_aggregate_identity==PAYMENT.obligation_identity
    assert task.correlation_id.value==payment_reference(PAYMENT)+':0'
    assert '18,000' in task.payload_json and '第一期' not in task.payload_json
    unit.commit.assert_called_once();unit.audit.append.assert_called_once()


def test_replay_returns_original_work_even_after_finance_changed():
    unit=Unit()
    unit.payment_overdue_reminders.existing.return_value=SimpleNamespace(task_id=SimpleNamespace(value=8),status=SimpleNamespace(value='sent'),
        request=SimpleNamespace(source_aggregate_type='manual_payment_overdue_reminder',source_aggregate_identity=PAYMENT.obligation_identity,correlation_id=SimpleNamespace(value=payment_reference(PAYMENT)+':0')))
    assert PaymentOverdueReminderApplication(lambda:unit,lambda:NOW).send(PAYMENT,'key',ActorContext('union'))==(8,'sent')
    unit.payment_overdue_reminders.payment.assert_not_called();unit.delivery_tasks.enqueue.assert_not_called()


@pytest.mark.parametrize('stage,label',[('deposit','訂金'),('first','第一期款'),('second','第二期款')])
def test_copy_has_only_selected_stage_remaining(stage,label):
    assert reminder_text(replace(PAYMENT,payment_stage=stage))==f'本案{label}尚有 NT$ 18,000 未確認入帳，請協助確認繳款，謝謝。'

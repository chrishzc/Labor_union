"""Queue eligibility queries retain each obligation and never mutate its work."""
from datetime import date, datetime, timezone
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.payment_overdue_reminder_repository import MySqlPaymentOverdueReminderRepository
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
from subsystems.line.payment_overdue_reminders import ReminderRecipient, SOURCE_TYPE


PAYMENT=OverdueClientPayment('CASE-1','deposit','CASE-1:deposit',3,7,date(2032,5,10),18000)


class Cursor:
    def __init__(self, connection):
        self.cursor=connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self,*_):
        self.cursor.close()

    def execute(self,sql,parameters=()):
        # SQLite exercises query predicates; native locking is tested on MySQL.
        self.cursor.execute(sql.replace(' FOR UPDATE','').replace('%s','?'),parameters)

    def fetchone(self):
        row=self.cursor.fetchone()
        if row is None:
            return None
        result=dict(row)
        if 'scheduled_at_utc' in result:
            result['scheduled_at_utc']=datetime.fromisoformat(result['scheduled_at_utc'])
        return result


@pytest.fixture
def repository():
    raw=sqlite3.connect(':memory:')
    raw.row_factory=sqlite3.Row
    raw.create_function('SUBSTRING_INDEX',3,lambda value,delimiter,count:delimiter.join(value.split(delimiter)[:count]))
    raw.execute('CREATE TABLE client_obligations(obligation_identity TEXT,case_no TEXT,obligation_type TEXT)')
    raw.execute('CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY,source_aggregate_type TEXT,'
                'source_aggregate_identity TEXT,processing_status TEXT,scheduled_at_utc TIMESTAMP)')
    repository=MySqlPaymentOverdueReminderRepository(SimpleNamespace(cursor=lambda:Cursor(raw)))
    repository.payments=SimpleNamespace(list=Mock(return_value=((PAYMENT,),1)))
    repository.recipient=Mock(return_value=ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId('U'+'1'*32)),0))
    yield repository,raw
    raw.close()


@pytest.mark.parametrize('status,blocked',[
    ('pending',True),('processing',True),('retryable_failed',True),
    ('sent',False),('failed',False),('cancelled',False),
])
def test_in_flight_queue_state_disables_send_without_hiding_or_writing_todo(repository,status,blocked):
    repo,raw=repository
    raw.execute('INSERT INTO line_delivery_tasks VALUES (1,?,?,?,?)',
                (SOURCE_TYPE,PAYMENT.obligation_identity,status,datetime(2032,5,10,16,tzinfo=timezone.utc).isoformat()))
    raw.commit()
    writes=raw.total_changes
    assert repo.has_pending(PAYMENT.obligation_identity,lock=True) is blocked
    items,total=repo.list(date(2032,5,11),1,25)
    assert total==1 and len(items)==1 and items[0].payment==PAYMENT
    assert items[0].can_send is (not blocked)
    assert (items[0].unavailable_reason is not None) is blocked
    assert items[0].last_reminder.status==status
    assert raw.total_changes==writes


@pytest.mark.parametrize('source,identity',[
    (SOURCE_TYPE,'CASE-1:first'),(SOURCE_TYPE,'CASE-2:deposit'),
    ('client_deposit_reminder',PAYMENT.obligation_identity),
])
def test_pending_work_for_another_obligation_or_source_does_not_block(repository,source,identity):
    repo,raw=repository
    raw.execute('INSERT INTO line_delivery_tasks VALUES (1,?,?,?,?)',(source,identity,'pending','2032-05-10T16:00:00+00:00'))
    assert not repo.has_pending(PAYMENT.obligation_identity,lock=True)
    items,total=repo.list(date(2032,5,11),1,25)
    assert total==1 and items[0].can_send and items[0].unavailable_reason is None


def test_older_pending_work_still_blocks_when_latest_work_is_terminal(repository):
    repo,raw=repository
    for identity,status in [(1,'pending'),(2,'cancelled')]:
        raw.execute('INSERT INTO line_delivery_tasks VALUES (?,?,?,?,?)',
                    (identity,SOURCE_TYPE,PAYMENT.obligation_identity,status,'2032-05-10T16:00:00+00:00'))
    items,_=repo.list(date(2032,5,11),1,25)
    assert items[0].last_reminder.status=='cancelled'
    assert not items[0].can_send

"""Current calendar gaps and manual group delivery, isolated localhost DB + fake LINE only."""
from datetime import date, datetime, timedelta, UTC
from uuid import uuid4
import os
import runpy
import pytest

from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from infrastructure.mysql.service_day_log_reminder_repository import MySqlServiceDayLogReminderRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from domains.scheduling.service_day_log import ServiceDayLogIntent
from subsystems.scheduling.service_day_log_workflow import ApplyServiceDayLog, ServiceDayLogApplication
from subsystems.line.service_day_log_reminders import ServiceDayLogReminderApplication, SendServiceDayLogReminder, SOURCE_TYPE

DATABASE=os.getenv('SERVICE_START_TEST_DB')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicit disposable localhost DB')
support=runpy.run_path('tests/domains/external-integration/subsystems/line/infrastructure/test_service_start_day_mysql.py')
http=support['http']
existing=support['existing'];rows,write,checked=support['rows'],support['write'],support['checked']
START=date(2033,5,4)
NOW=datetime(2033,5,7,12,tzinfo=UTC)  # 20:00 Taipei: four completed day shifts


def prepared(http,*,count=1):
    assert DATABASE.startswith('lu_test_') and mysql_adapter.DB_CONFIG['database']==DATABASE
    assert mysql_adapter.DB_CONFIG['host'] in ('127.0.0.1','localhost')
    case,staff,segments=existing['seed_case'](http,count=count)
    for index,segment in enumerate(segments):
        checked(existing['submit'](http,case,staff[index],segment,start=(START+timedelta(days=index*30)).isoformat())[0])
    write('UPDATE orders SET requires_cooking=0 WHERE case_no=%s',(case,))
    return case,staff


def gaps(case,now=NOW):
    c=mysql_adapter.get_connection()
    try:return MySqlServiceDayLogRepository(c).missing_runs(now,case_no=case)[0]
    finally:c.close()


def app(connection,now=NOW):
    return ServiceDayLogReminderApplication(MySqlServiceDayLogReminderRepository(connection),
                                            lambda:MySqlUnitOfWork(connection),lambda:now)


def command(case,gap,key=None):
    return SendServiceDayLogReminder(case,gap.staff_id,gap.missing_from,gap.missing_through,key or uuid4().hex)


def send(case,gap,key=None):
    c=mysql_adapter.get_connection()
    try:return app(c).send(command(case,gap,key))
    finally:c.close()


def fill(case,staff,day):
    assignment=rows('SELECT ss.assignment_id FROM staff_schedule ss JOIN scheduling_aggregates g '
                    'ON g.case_no=ss.case_no AND g.effective_generation_id=ss.generation_id '
                    'WHERE ss.case_no=%s AND ss.staff_id=%s AND ss.work_date=%s AND ss.is_work_day=1',
                    (case,staff[0],day))[0]['assignment_id']
    c=mysql_adapter.get_connection()
    try:
        application=ServiceDayLogApplication(MySqlServiceDayLogRepository(c),lambda:MySqlUnitOfWork(c))
        return application.apply(ApplyServiceDayLog(staff[0],staff[1],assignment,
                     ServiceDayLogIntent(day,'合成驗證：服務正常'),uuid4().hex))
    finally:c.close()


def task(case):return rows('SELECT * FROM line_delivery_tasks WHERE source_aggregate_type=%s AND source_aggregate_identity=%s ORDER BY id',(SOURCE_TYPE,case))


def test_three_days_never_list_four_days_list_without_enqueue_and_manual_exact_group(http):
    case,staff=prepared(http)
    assert not gaps(case,NOW-timedelta(days=1))
    gap=gaps(case)[0];assert gap.consecutive_days==4
    assert (gap.missing_from,gap.missing_through)==(START,START+timedelta(days=3))
    c=mysql_adapter.get_connection()
    try:
        items,total=app(c).list(1,100)
        for page in range(2,(total+99)//100+1):
            more,_=app(c).list(page,100)
            items+=more
        assert total>=1 and any(item.gap.case_no==case and item.group_label==f'案件 {case} 群組' for item in items)
    finally:c.close()
    assert not task(case)
    result=send(case,gap,'one-click-'+case)
    assert send(case,gap,'one-click-'+case).task_id==result.task_id
    notices=task(case);assert len(notices)==1 and notices[0]['recipient_type']=='group'
    group=rows('SELECT group_id FROM line_order_group_bindings WHERE case_no=%s',(case,))[0]['group_id']
    assert notices[0]['recipient_identity']==group
    worker=support['TaskScopedWorker'](result.task_id.value,now=NOW)
    worker.run_once();assert len(worker.calls)==1


@pytest.mark.parametrize('offset',[1,2,3])
def test_off_day_breaks_calendar_run_instead_of_accumulating_workdays(http,offset):
    case,_=prepared(http)
    write('UPDATE staff_schedule SET is_work_day=0 WHERE case_no=%s AND work_date=%s',(case,START+timedelta(days=offset)))
    assert not gaps(case)


def test_fill_breaks_run_and_future_prefill_is_allowed_no_edit(http):
    case,staff=prepared(http)
    fill(case,staff[0],START+timedelta(days=1))
    assert not gaps(case)
    future=START+timedelta(days=20)
    result=fill(case,staff[0],future)
    assert result.service_date==future.isoformat()
    with pytest.raises(ValueError,match='idempotency_conflict'):
        # Same day with a new command cannot replace an existing submitted log.
        c=mysql_adapter.get_connection()
        try:
            assignment=rows('SELECT assignment_id FROM scheduling_service_day_logs WHERE id=%s',(result.log_id,))[0]['assignment_id']
            ServiceDayLogApplication(MySqlServiceDayLogRepository(c),lambda:MySqlUnitOfWork(c)).apply(
              ApplyServiceDayLog(staff[0][0],staff[0][1],assignment,ServiceDayLogIntent(future,'試圖修改'),uuid4().hex))
        finally:c.close()


@pytest.mark.parametrize('change',['fill','group','same_group_version','release','reschedule','cancel'])
def test_queued_work_rechecks_current_logs_schedule_and_group_before_fake_provider(http,change):
    case,staff=prepared(http);gap=gaps(case)[0];result=send(case,gap)
    if change=='fill':fill(case,staff[0],START+timedelta(days=1))
    elif change=='group':write('UPDATE line_order_group_bindings SET group_id=%s,aggregate_version=aggregate_version+1 WHERE case_no=%s',('C'+uuid4().hex,case))
    elif change=='same_group_version':write('UPDATE line_order_group_bindings SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
    elif change=='release':write("UPDATE line_order_group_bindings SET binding_status='released' WHERE case_no=%s",(case,))
    elif change=='reschedule':
        write('UPDATE staff_schedule SET is_work_day=0 WHERE case_no=%s AND work_date=%s',(case,START))
    else:write("UPDATE orders SET status='訂單取消' WHERE case_no=%s",(case,))
    worker=support['TaskScopedWorker'](result.task_id.value,now=NOW)
    worker.run_once();assert not worker.calls
    assert task(case)[0]['processing_status']=='cancelled'


def test_cross_midnight_does_not_count_day_before_service_ends(http):
    case,_=prepared(http)
    write("UPDATE orders SET service_start_time='20:00:00',service_end_time='08:00:00',service_end_day_offset=1 WHERE case_no=%s",(case,))
    assert not gaps(case,datetime(2033,5,7,23,tzinfo=UTC)) # next Taipei day 07:00: only 3 shifts ended
    assert gaps(case,datetime(2033,5,8,1,tzinfo=UTC))[0].consecutive_days==4


def test_later_filled_day_does_not_hide_unresolved_four_day_interval(http):
    case,staff=prepared(http);fill(case,staff[0],START+timedelta(days=4))
    run=gaps(case,NOW+timedelta(days=1))[0]
    assert run.consecutive_days==4


def test_month_boundary_contiguous_dates_are_one_run(http):
    case,staff=prepared(http)
    # Official writer shifts the selected service segment; no fake LINE send occurs.
    # Date-run logic reads current effective generation; synthetic work-date shifts stay in this fixture.
    write('UPDATE staff_schedule SET work_date=DATE_SUB(work_date,INTERVAL 5 DAY) WHERE case_no=%s',(case,))
    run=gaps(case,NOW-timedelta(days=5))[0]
    assert run.missing_from==date(2033,4,29) and run.missing_through==date(2033,5,2)


def test_provider_fresh_check_cannot_reuse_an_older_repeatable_read_snapshot(http):
    case,staff=prepared(http);gap=gaps(case)[0]
    c=mysql_adapter.get_connection()
    try:
        with c.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM scheduling_service_day_logs WHERE case_no=%s',(case,))
            cursor.fetchone()  # Establish the same consistent snapshot as a delivery-task read.
        fill(case,staff[0],START+timedelta(days=1))
        assert MySqlServiceDayLogReminderRepository(c).recipient(command(case,gap),NOW) is None
    finally:c.close()


def test_missing_group_is_an_internal_todo_only_and_click_cannot_create_job(http):
    case,_=prepared(http);gap=gaps(case)[0]
    write("UPDATE line_order_group_bindings SET binding_status='released' WHERE case_no=%s",(case,))
    with pytest.raises(ValueError,match='no_longer_applicable'):send(case,gap)
    assert not task(case)

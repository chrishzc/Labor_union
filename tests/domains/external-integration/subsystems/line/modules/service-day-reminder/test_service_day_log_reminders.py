"""Human-only case-group reminders and direct diary submission acceptance."""
from contextlib import nullcontext
from datetime import date, datetime, UTC
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from domains.line.identities import LineDeliveryTaskId
from domains.scheduling.service_day_log import ServiceDayLogIntent
from shared_kernel.identities import CorrelationId
from subsystems.line.service_day_log_reminders import (
    ServiceDayLogReminderApplication, SendServiceDayLogReminder,
    service_day_log_reminder_delivery_is_current, SOURCE_TYPE,
)
from subsystems.scheduling.service_day_log_workflow import ApplyServiceDayLog, ServiceDayLogWorkflow

NOW = datetime(2032,5,8,12,tzinfo=UTC)
COMMAND = SendServiceDayLogReminder('CASE-1', 8, date(2032,5,4), date(2032,5,7), 'click-1')


def application():
    repository = Mock()
    repository.replay.return_value = None
    repository.recipient.return_value = ('C-test-case-group', '測試月嫂', 3)
    unit = Mock()
    return ServiceDayLogReminderApplication(repository, lambda: nullcontext(unit), lambda: NOW), repository, unit


def test_list_is_read_only_and_does_not_enqueue_or_commit():
    app, repository, unit = application()
    app.list(2, 25)
    repository.list.assert_called_once_with(NOW,2,25)
    repository.recipient.assert_not_called()
    repository.enqueue.assert_not_called()
    unit.commit.assert_not_called()


def test_pending_query_previews_the_same_message_as_the_existing_sender():
    from infrastructure.mysql.service_day_log_reminder_repository import MySqlServiceDayLogReminderRepository
    from subsystems.line.service_day_log_reminders import reminder_text
    gap=SimpleNamespace(staff_id=8,case_no='CASE-1')
    cursor=Mock()
    cursor.__enter__=Mock(return_value=cursor)
    cursor.__exit__=Mock(return_value=False)
    cursor.fetchall.return_value=[{'id':8,'name':'測試月嫂'}]
    connection=Mock();connection.cursor.return_value=cursor
    repository=MySqlServiceDayLogReminderRepository(connection)
    repository.message = reminder_text
    repository.scheduling=SimpleNamespace(missing_runs=lambda *args,**kwargs:((gap,),1))
    repository._group=lambda case:None
    result,total=repository.list(NOW,1,25)
    assert total==1 and result[0].message==reminder_text('測試月嫂')
    assert not result[0].can_send
    connection.commit.assert_not_called()


def test_click_queues_one_short_case_group_message_and_commits():
    app,repository,unit=application()
    app.send(COMMAND)
    request=repository.enqueue.call_args.args[0]
    assert request.recipient.recipient_type.value=='group'
    assert request.recipient.identity.value=='C-test-case-group'
    assert '請 測試月嫂 補上尚未填寫的服務日誌，謝謝。' in request.payload_json
    assert request.source_aggregate_type==SOURCE_TYPE
    assert request.correlation_id.value.endswith(':3')
    unit.commit.assert_called_once()


def test_sender_uses_the_composed_copy_reader_with_fresh_staff_name():
    _, repository, unit = application()
    reader = Mock(side_effect=lambda name: f"請 {name} 確認服務日誌紀錄。")
    app = ServiceDayLogReminderApplication(repository, lambda: nullcontext(unit), lambda: NOW, reader)
    app.send(COMMAND)
    reader.assert_called_once_with('測試月嫂')
    assert '請 測試月嫂 確認服務日誌紀錄。' in repository.enqueue.call_args.args[0].payload_json


def test_replay_returns_original_task_without_rechecking_or_enqueue():
    app,repository,unit=application()
    repository.replay.return_value='original-receipt'
    assert app.send(COMMAND)=='original-receipt'
    repository.recipient.assert_not_called()
    repository.enqueue.assert_not_called()


def test_filled_or_missing_group_cannot_enqueue():
    app,repository,unit=application()
    repository.recipient.return_value=None
    with pytest.raises(ValueError,match='no_longer_applicable'):app.send(COMMAND)
    repository.enqueue.assert_not_called()
    unit.commit.assert_not_called()


@pytest.mark.parametrize('automatic,current,expected',[(False,True,True),(False,False,False),(True,True,False)])
def test_provider_gate_cancels_stale_manual_and_all_retired_automatic(automatic,current,expected):
    request=SimpleNamespace(source_aggregate_type='case_staff_assignment' if automatic else SOURCE_TYPE,
      correlation_id=CorrelationId('line-notification:scheduling-service-day-checkpoint-outbox:91' if automatic else COMMAND.correlation.value))
    task=SimpleNamespace(request=request,task_id=LineDeliveryTaskId(1))
    unit=Mock();unit.service_day_log_reminders.delivery_is_current.return_value=current
    assert service_day_log_reminder_delivery_is_current(unit,task,NOW) is expected
    assert unit.delivery_tasks.cancel.call_count==(0 if expected else 1)


def test_direct_submit_needs_no_preview_and_locks_owner_facts_once():
    repository=Mock()
    repository.load_replay.return_value=None
    repository.load_assignment.return_value={'case_no':'CASE-1','requires_cooking':False}
    command=ApplyServiceDayLog(8,'U-test',12,ServiceDayLogIntent(date(2099,1,1),'正常'),'direct-key')
    workflow=ServiceDayLogWorkflow(repository)
    workflow.apply(command)
    repository.load_assignment.assert_called_once_with(8,12,date(2099,1,1),for_update=True)
    saved=repository.submit.call_args.args[0]
    assert saved.preview_fingerprint is not None  # server-only replay digest, not a UI prerequisite
    repository.load_replay.return_value='original receipt'
    assert workflow.apply(command)=='original receipt'
    assert repository.load_assignment.call_count==1


def test_direct_cooking_submit_still_requires_photo():
    repository=Mock();repository.load_replay.return_value=None
    repository.load_assignment.return_value={'case_no':'CASE-1','requires_cooking':True}
    with pytest.raises(ValueError,match='meal_photo_required'):
        ServiceDayLogWorkflow(repository).apply(ApplyServiceDayLog(8,'U-test',12,
            ServiceDayLogIntent(date(2032,5,4),'正常'),'direct-key'))
    repository.submit.assert_not_called()


def test_admin_transport_requires_union_permission_and_rejects_supplied_recipient():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from api.routes import line_order_groups
    from api.dependencies.admin_auth import require_customer_service_handler, require_line_order_group_reader
    from api.dependencies.service_day_log_reminders import get_service_day_log_reminders
    app=FastAPI();app.include_router(line_order_groups.router)
    application=Mock()
    def denied():raise HTTPException(403,detail='forbidden')
    app.dependency_overrides[require_customer_service_handler]=denied
    app.dependency_overrides[require_line_order_group_reader]=denied
    app.dependency_overrides[get_service_day_log_reminders]=lambda:application
    body=dict(case_no='CASE-1',staff_id=8,missing_from='2032-05-04',missing_through='2032-05-07',idempotency_key='click')
    with TestClient(app) as client:
        assert client.get('/api/v1/line/order-groups/log-reminders').status_code==403
        assert client.post('/api/v1/line/order-groups/log-reminders/send',json=body).status_code==403
        application.send.assert_not_called();application.list.assert_not_called()
        app.dependency_overrides[require_customer_service_handler]=lambda:object()
        assert client.post('/api/v1/line/order-groups/log-reminders/send',json={**body,'group_id':'C-forged'}).status_code==422
        application.send.assert_not_called()
        application.send.side_effect=ValueError('service_day_log_reminder_no_longer_applicable')
        response=client.post('/api/v1/line/order-groups/log-reminders/send',json=body)
        assert response.status_code==409 and response.json()['detail']['error']['category']=='conflict'

"""Authenticated schedule editing; reuses the canonical configuration CAS writer."""
from dataclasses import asdict
import json
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from pymysql.err import OperationalError

from api.dependencies.admin_auth import admin_actor_context, require_line_configuration_reader, require_line_configuration_manager
from api.dependencies.line_runtime import get_line_configuration_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from domains.line.configuration import LineConfigurationKind, LineConfigurationRevisionConflict
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import LineConfigurationQueryUnavailableError
from subsystems.line.message_configuration import LineMessageConfigurationError
from subsystems.line.payment_reminder_schedule import PaymentReminderSchedule, parse_schedule

router=APIRouter()
_TIME=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$'


class PaymentReminderScheduleBody(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    deposit_mode: Literal['immediate','daily']
    deposit_time: str=Field(pattern=_TIME)
    first_time: str=Field(pattern=_TIME)
    second_time: str=Field(pattern=_TIME)
    overdue_time: str=Field(pattern=_TIME)


class PaymentReminderSettingsView(BaseModel):
    revision: int
    schedule: PaymentReminderScheduleBody
    timezone: Literal['Asia/Taipei']='Asia/Taipei'
    followup_after_hours: Literal[24]=24
    followup_limit: Literal[1]=1


class PaymentReminderSettingsUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    expected_revision: int=Field(ge=0)
    schedule: PaymentReminderScheduleBody
    idempotency_key: str=Field(min_length=1,max_length=100)

    @field_validator('idempotency_key')
    @classmethod
    def canonical_operation_key(cls,value):
        IdempotencyKey('payment-schedule:'+value)
        return value


def _view(snapshot):
    definition=json.loads(snapshot.definition_json)
    schedule=parse_schedule(definition['payment_reminders']) if 'payment_reminders' in definition else PaymentReminderSchedule()
    return PaymentReminderSettingsView(revision=snapshot.revision.value,schedule=PaymentReminderScheduleBody(**asdict(schedule)))


@router.get('/schedule',response_model=BaseResponse[PaymentReminderSettingsView])
def get_payment_reminder_schedule(principal: AdminPrincipal=Depends(require_line_configuration_reader)):
    try:
        snapshot=get_line_configuration_application().get(LineConfigurationKind.MESSAGE_SCHEDULES,admin_actor_context(principal))
        return BaseResponse(data=_view(snapshot))
    except (OperationalError,LineConfigurationQueryUnavailableError,LineMessageConfigurationError) as error:
        raise typed_http_error(503,'unavailable','payment_schedule_unavailable','提醒排程暫時無法取得，請稍後重試。','payment-reminder-schedule') from error


@router.put('/schedule',response_model=BaseResponse[PaymentReminderSettingsView])
def save_payment_reminder_schedule(payload: PaymentReminderSettingsUpdate,principal: AdminPrincipal=Depends(require_line_configuration_manager)):
    application=get_line_configuration_application()
    actor=admin_actor_context(principal)
    try:
        key=IdempotencyKey('payment-schedule:'+payload.idempotency_key)
        applied=application.get_applied(LineConfigurationKind.MESSAGE_SCHEDULES,key,actor)
        if applied is not None:
            view=_view(applied)
            if view.revision!=payload.expected_revision+1 or view.schedule!=payload.schedule:
                raise LineConfigurationRevisionConflict('payment_schedule_idempotency_conflict')
            return BaseResponse(data=view,message='提醒排程已儲存。')
        snapshot=application.get(LineConfigurationKind.MESSAGE_SCHEDULES,actor)
        definition=json.loads(snapshot.definition_json)
        definition.setdefault('version',1)
        definition.setdefault('timezone','Asia/Taipei')
        definition.setdefault('schedules',[])
        definition['payment_reminders']=payload.schedule.model_dump()
        result=application.apply(kind=LineConfigurationKind.MESSAGE_SCHEDULES,
            expected_revision=LineConfigurationRevision(payload.expected_revision),definition=definition,actor=actor,
            reason='帳務繳款提醒排程',idempotency_key=key,
            correlation_id=CorrelationId('payment-schedule:'+uuid4().hex))
        return BaseResponse(data=_view(result.snapshot),message='提醒排程已儲存。')
    except (LineConfigurationRevisionConflict,RuntimeError) as error:
        if isinstance(error,RuntimeError) and str(error) not in {'line_configuration_revision_conflict','line_configuration_idempotency_conflict'}:
            raise
        raise typed_http_error(409,'conflict','payment_schedule_changed','排程已由其他人更新，請重新讀取後再儲存。','payment-reminder-schedule') from error
    except LineMessageConfigurationError as error:
        raise typed_http_error(422,'validation','payment_schedule_invalid','提醒排程時間不完整或不正確。','payment-reminder-schedule') from error
    except (OperationalError,LineConfigurationQueryUnavailableError) as error:
        raise typed_http_error(503,'unavailable','payment_schedule_unavailable','提醒排程暫時無法儲存，請稍後重試。','payment-reminder-schedule') from error

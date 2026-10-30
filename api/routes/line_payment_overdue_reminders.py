"""Union-only overdue list and one-click durable manual reminder commands."""
from dataclasses import asdict
from datetime import date, datetime
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from api.dependencies.admin_auth import admin_actor_context, require_customer_service_handler
from api.dependencies.payment_overdue_reminders import get_payment_overdue_reminders
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
from subsystems.line.payment_overdue_reminders import PaymentOverdueReminderConflict

router = APIRouter(prefix='/api/v1/line/payment-overdue-reminders',tags=['LINE Payment Overdue Reminders'])
from api.routes.line_payment_reminder_settings import router as settings_router
router.include_router(settings_router)


class PaymentSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1,max_length=50)
    payment_stage: Literal['deposit','first','second']
    obligation_identity: str = Field(min_length=1,max_length=191)
    projection_version: int = Field(ge=0)
    obligation_event_id: int = Field(gt=0)
    due_date: date
    remaining_amount_ntd: int = Field(gt=0)


class ReminderSend(PaymentSnapshot):
    idempotency_key: str = Field(min_length=1,max_length=100)


class LastReminderView(BaseModel):
    requested_at: datetime
    status: str


class ReminderItemView(BaseModel):
    payment: PaymentSnapshot
    overdue_days: int
    recipient_label: str
    can_send: bool
    unavailable_reason: str | None
    last_reminder: LastReminderView | None


class ReminderPageView(BaseModel):
    items: list[ReminderItemView]
    total: int
    page: int
    page_size: int


class ReminderReceiptView(BaseModel):
    task_id: int
    status: str


@router.get('', response_model=BaseResponse[ReminderPageView])
def list_reminders(page: int=Query(1,ge=1),page_size: int=Query(25,ge=1,le=100),
    principal: AdminPrincipal=Depends(require_customer_service_handler),application=Depends(get_payment_overdue_reminders)):
    items,total = application.list(page,page_size)
    return BaseResponse(data={'items':[asdict(item) for item in items],'total':total,'page':page,'page_size':page_size})


@router.post('/send', response_model=BaseResponse[ReminderReceiptView])
def send_reminder(body: ReminderSend,principal: AdminPrincipal=Depends(require_customer_service_handler),
                  application=Depends(get_payment_overdue_reminders)):
    try:
        expected = OverdueClientPayment(**body.model_dump(exclude={'idempotency_key'}))
        identity,status = application.send(expected,body.idempotency_key,admin_actor_context(principal))
    except PaymentOverdueReminderConflict as error:
        raise typed_http_error(409,'conflict',str(error),'款項或收件對象已更新，請重新整理後再操作。','payment-overdue-reminder') from error
    return BaseResponse(data={'task_id':identity,'status':status})

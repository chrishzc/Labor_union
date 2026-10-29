"""Verified customer payment views and capability-scoped staff reminder commands."""
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.line_deposit import get_deposit_notifications
from api.dependencies.line_identity import get_liff_token_verifier
from api.error_contracts import typed_http_error
from api.routes.line_mobile_admin import _mobile_admin_context
from api.schemas.base import BaseResponse
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import IdempotencyKey
from subsystems.line.capabilities import LineCapability, LineCapabilityDeniedError
from subsystems.line.deposit_notifications import DepositNotificationConflict, DepositPaymentForbidden

router = APIRouter(tags=['LINE Deposit Payment'])
page_router = APIRouter(tags=['LINE Deposit Payment Page'])


class _Auth(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    line_id_token: str = Field(min_length=1, max_length=4096)


class DepositCustomerQuery(_Auth):
    case_no: str = Field(min_length=1, max_length=50, pattern=r'^[A-Za-z0-9_-]+$')


class DepositReminderSend(DepositCustomerQuery):
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class DepositStaffQuery(_Auth):
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=25, ge=1, le=50)
    settled: bool | None = None
    case_no: str | None = Field(default=None, min_length=1, max_length=50)


class DepositPaymentView(BaseModel):
    case_no: str
    amount_ntd: int
    status: Literal['unpaid', 'settled']
    due_date: date | None
    bank_code: str | None
    virtual_account: str | None
    received_on: date | None


class DepositStaffItem(BaseModel):
    case_no: str
    amount_ntd: int
    due_date: date | None
    expected_version: int
    settled: bool
    line_bound: bool
    ready: bool
    delivery_status: str | None
    unavailable_reason: str | None = None


def deposit_reminder_blocker(application, payment, line_bound: bool) -> str | None:
    reasons = []
    if not line_bound:
        reasons.append('客戶尚未綁定 LINE，請先聯絡客戶完成身分綁定。')
    if not payment.settled:
        labels = {'due_date':'繳費到期日','virtual_account':'案件虛擬帳號','bank_code':'銀行代碼','liff':'LINE 繳費頁面設定'}
        missing = application.missing_reminder_fields(payment)
        if missing:
            reasons.append('尚未完成：'+'、'.join(labels[field] for field in missing)+'。請核對案件帳務及系統設定。')
    return ' '.join(reasons) or None


class DepositStaffPage(BaseModel):
    items: list[DepositStaffItem]
    page: int
    has_next: bool
    total: int = Field(ge=0)
    pending_total: int = Field(ge=0)
    unpaid_total: int = Field(ge=0)
    settled_total: int = Field(ge=0)


class DepositReminderReceipt(BaseModel):
    task_id: int
    delivery_status: str


@page_router.get('/line-deposit-payment')
def deposit_payment_page():
    return FileResponse(Path(__file__).resolve().parents[2] / 'line/static/deposit_payment.html', headers={'Cache-Control': 'no-store'})


@router.post('/api/v1/line/deposit-payment/query', response_model=BaseResponse[DepositPaymentView])
def query_deposit_payment(payload: DepositCustomerQuery, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        identity = get_liff_token_verifier().verify(payload.line_id_token)
        application = get_deposit_notifications()
        payment = application.query_customer(payload.case_no, identity.line_user_id)
        return BaseResponse(data=DepositPaymentView(
            case_no=payment.case_no, amount_ntd=payment.amount_ntd,
            status='settled' if payment.settled else 'unpaid', due_date=payment.due_date,
            bank_code=application.bank_code, virtual_account=payment.virtual_account,
            received_on=payment.received_on,
        ))
    except _ERRORS as error:
        _raise_error(error)


@router.post('/api/v1/line/mobile-admin/deposit-payments', response_model=BaseResponse[DepositStaffPage])
def deposit_staff_followups(payload: DepositStaffQuery):
    _mobile_admin_context(payload.line_id_token, LineCapability.TASK_READ)
    try:
        application = get_deposit_notifications()
        with open_line_unit_of_work() as uow:
            result = uow.deposit_notifications.followups(page=payload.page, page_size=payload.page_size, settled=payload.settled, **({"case_no":payload.case_no} if payload.case_no else {}))
        return BaseResponse(data=DepositStaffPage(items=[DepositStaffItem(
            case_no=item.payment.case_no, amount_ntd=item.payment.amount_ntd, due_date=item.payment.due_date,
            expected_version=item.payment.obligation_version, settled=item.payment.settled,
            line_bound=item.line_bound, ready=application.ready(item.payment), delivery_status=item.delivery_status,
            unavailable_reason=deposit_reminder_blocker(application,item.payment,item.line_bound),
        ) for item in result.items], page=payload.page, has_next=result.has_next, total=result.page_total,
            pending_total=result.total, unpaid_total=result.unpaid_total, settled_total=result.settled_total))
    except _ERRORS as error:
        _raise_error(error)


@router.post('/api/v1/line/mobile-admin/deposit-payments/remind', response_model=BaseResponse[DepositReminderReceipt])
def send_deposit_reminder(payload: DepositReminderSend):
    _, actor = _mobile_admin_context(payload.line_id_token, LineCapability.TASK_SEND)
    try:
        task_id, status = get_deposit_notifications().send_reminder(
            payload.case_no, payload.expected_version, IdempotencyKey(payload.idempotency_key), actor,
        )
        return BaseResponse(data=DepositReminderReceipt(task_id=task_id, delivery_status=status),
                            message='已建立寄送工作，尚未證明送達。')
    except _ERRORS as error:
        _raise_error(error)


def _raise_error(error):
    correlation = 'line-deposit-payment'
    if isinstance(error, (LiffVerificationUnavailableError, OperationalError)):
        raise typed_http_error(503, 'unavailable', 'deposit_payment_unavailable', '目前無法取得繳費資料，請稍後再試。', correlation, retryable=True) from error
    if isinstance(error, InvalidLiffTokenError):
        raise typed_http_error(401, 'forbidden', 'liff_token_invalid', '請重新從 LINE 開啟頁面。', correlation) from error
    if isinstance(error, (DepositPaymentForbidden, LineCapabilityDeniedError)):
        raise typed_http_error(403, 'forbidden', 'deposit_payment_forbidden', '無法查看或操作此案件的繳費資料。', correlation) from error
    if str(error) == 'deposit_contract_not_completed':
        raise typed_http_error(409, 'conflict', str(error), '客戶與所有月嫂尚未完成簽約，請完成雙方簽約後再提醒繳款。', correlation) from error
    raise typed_http_error(409, 'conflict', str(error), '繳費資料或狀態已變更，請重新讀取待辦。', correlation) from error


_ERRORS = (InvalidLiffTokenError, LiffVerificationUnavailableError, OperationalError,
           DepositPaymentForbidden, DepositNotificationConflict, LineCapabilityDeniedError)

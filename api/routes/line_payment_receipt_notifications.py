"""Authenticated receipt todo Query and explicit human Send; no provider calls."""
from dataclasses import asdict
from datetime import datetime, UTC
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError
from api.dependencies.admin_auth import admin_actor_context, require_customer_service_handler
from api.dependencies.line_deposit import get_deposit_notifications
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.capabilities import LineCapabilityDeniedError
from subsystems.line.deposit_notifications import DepositNotificationConflict
from subsystems.line.message_configuration import LineMessageConfigurationError
from subsystems.line.payment_receipt_notifications import PaymentReceiptSnapshot, PaymentReceiptConflict, PaymentReceiptNotificationApplication

router=APIRouter()


def application():
    return PaymentReceiptNotificationApplication(open_line_unit_of_work,lambda:datetime.now(UTC),get_deposit_notifications())


class ReceiptPayment(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    case_no: str=Field(min_length=1,max_length=50,pattern=r'^[A-Za-z0-9_-]+$')
    payment_stage: Literal['deposit','second']
    settlement_identity: str=Field(min_length=1,max_length=128)
    amount_ntd: int=Field(gt=0)
    source_version: int=Field(ge=0)
    source_reference: str=Field(min_length=1,max_length=191)


class ReceiptTodo(BaseModel):
    payment: ReceiptPayment
    can_send: bool
    unavailable_reason: str | None
    delivery_status: str | None


class ReceiptPage(BaseModel):
    items: list[ReceiptTodo]
    total: int
    page: int
    page_size: int


class ReceiptResult(BaseModel):
    task_id: int
    status: str


@router.get('/receipts',response_model=BaseResponse[ReceiptPage])
def list_receipts(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),
    principal:AdminPrincipal=Depends(require_customer_service_handler),app=Depends(application)):
    try:
        items,total=app.list(page,page_size)
        return BaseResponse(data={'items':[asdict(item) for item in items],'total':total,'page':page,'page_size':page_size})
    except OperationalError as error:
        raise typed_http_error(503,'unavailable','receipt_notice_unavailable','入帳通知待辦暫時無法取得，請稍後再試。','payment-receipt') from error


@router.post('/receipts/send',response_model=BaseResponse[ReceiptResult])
def send_receipt(body:ReceiptPayment,principal:AdminPrincipal=Depends(require_customer_service_handler),app=Depends(application)):
    try:
        task,status=app.send(PaymentReceiptSnapshot(**body.model_dump()),admin_actor_context(principal))
        return BaseResponse(data={'task_id':task,'status':status},message='已建立人工入帳通知寄送工作，尚未證明送達。')
    except (PaymentReceiptConflict,DepositNotificationConflict) as error:
        raise typed_http_error(409,'conflict',str(error),'帳款或寄送狀態已變更，請重新整理待辦。','payment-receipt') from error
    except LineCapabilityDeniedError as error:
        raise typed_http_error(403,'forbidden','receipt_notice_forbidden','目前帳號沒有發送通知的權限。','payment-receipt') from error
    except LineMessageConfigurationError as error:
        raise typed_http_error(409,'conflict','receipt_copy_unavailable','入帳通知內容目前不可用，請先確認提醒內容設定。','payment-receipt') from error
    except OperationalError as error:
        raise typed_http_error(503,'unavailable','receipt_notice_unavailable','寄送工作結果未確認，請以原操作確認結果。','payment-receipt') from error

"""Whole-period reconciliation; no provider sends or application/approval operations."""
from dataclasses import asdict
from datetime import date
import re
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator, ValidationError
from pydantic_core import PydanticCustomError
from pymysql import MySQLError
from pymysql.err import IntegrityError, OperationalError
from api.dependencies.admin_auth import admin_actor_context, require_system_admin
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse, JS_SAFE_INTEGER_MAX
from domains.government_subsidy.period_reconciliation import PeriodReconciliationConflict, SubsidyPeriod
from domains.government_subsidy.period_reconciliation import SubsidyPeriodLine
from infrastructure.mysql.government_subsidy_period_repository import MySqlGovernmentSubsidyPeriodRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.government_subsidy.period_reconciliation import PeriodReconciliationApplication,GovernmentDifferenceCommand,GovernmentAmountItem,GovernmentPeriodOperation,GovernmentAmountChange, ManualInitialPeriodReceipt

router = APIRouter(prefix='/api/v1/government-subsidy/periods', tags=['Government Subsidy Periods'])


def get_application():
    connection = get_connection()
    try:
        yield PeriodReconciliationApplication(MySqlGovernmentSubsidyPeriodRepository(connection), lambda: MySqlUnitOfWork(connection))
    finally:
        connection.close()


class PeriodBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    unit: Literal['month','quarter','year']
    year: int = Field(ge=1912,le=9998)
    index: int = Field(ge=1,le=12)
    bank_row_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1,max_length=100)


class ReversalBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    receipt_id: int = Field(gt=0)
    bank_row_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1,max_length=100)


class CoverageView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    receipt_id:int
    period:SubsidyPeriod
    amount_ntd:int
    recovered_advance_ntd:int
    label:str
    settled:bool=True
    source_label:Literal['人工補登']|None=None


class BalanceView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identity:str
    root_receipt_id:int
    kind:str
    case_no:str|None
    direction:str
    expected_ntd:int
    received_ntd:int
    recognized_ntd:int
    returned_ntd:int
    remaining_ntd:int
    refund_due_ntd:int
    settled:bool
    status:str


class PeriodView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    period:SubsidyPeriod
    version:int
    lines:list[SubsidyPeriodLine]
    total_ntd:int|None
    coverage:list[CoverageView]
    blocked_cases:list[str]
    recorded_lines:list[SubsidyPeriodLine]
    changed_cases:list[str]
    can_reconcile:bool
    label:str
    balances:list[BalanceView]=[]
    amount_controls:list[GovernmentAmountItem]=[]
    operations:list[GovernmentPeriodOperation]=[]
    amount_changes:list[GovernmentAmountChange]=[]


class BankRowView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:int
    paid_on:date|None
    amount_ntd:int


class BankPageView(BaseModel):
    items:list[BankRowView]


class CaseReceiptView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    receipt_id:int
    label:str
    amount_ntd:int
    recorded_case_amount_ntd:int
    recorded_service_end_date:date
    recovered_advance_ntd:int
    settled:bool=True
    source_label:Literal['人工補登']|None=None


class CaseCoverageView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_no:str
    service_end_date:date|None
    amount_ntd:int|None
    coverage:list[CaseReceiptView]


class ReceiptView(BaseModel):
    receipt_id:int


def _conflict(error):
    return typed_http_error(409,'conflict',str(error),'期間、案件或銀行資料已變動，請重新整理核對。','subsidy-period')


def _mutate(action):
    try:
        return action()
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error
    except (OperationalError,IntegrityError) as error:
        if error.args and error.args[0] in (1062,1205,1213):
            raise _conflict(PeriodReconciliationConflict('subsidy_period_write_conflict')) from error
        raise


@router.get('',response_model=BaseResponse[PeriodView])
def query_period(unit: Literal['month','quarter','year'],year: int=Query(ge=1912,le=9998),index: int=Query(ge=1,le=12),
                 principal=Depends(require_system_admin),application=Depends(get_application)):
    try:
        view = application.query(SubsidyPeriod(unit,year,index))
        return BaseResponse(data=_period_payload(view))
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error
    except ValueError as error:
        raise typed_http_error(422,'validation','subsidy_period_invalid','請選擇有效的月份、季度或年度。','subsidy-period') from error


def _period_payload(view):
    data=asdict(view)
    data['label']=view.period.label
    for coverage,item in zip(view.coverage,data['coverage']):
        item['label']=coverage.period.label
    for balance,item in zip(view.balances,data['balances']):
        item.update(remaining_ntd=balance.remaining_ntd,refund_due_ntd=balance.refund_due_ntd,settled=balance.settled,status=balance.status)
    return data


class DifferenceBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    unit:Literal['month','quarter','year']
    year:int=Field(ge=1912,le=9998)
    index:int=Field(ge=1,le=12)
    action:Literal['initial_receipt','receipt','refund','loss','manual_amount','adopt_calculation']
    identity:str=Field(default='',max_length=191)
    amount_ntd:int|None=Field(default=None,ge=0,le=9999999999)
    bank_row_id:int|None=Field(default=None,gt=0)
    handling:Literal['','exact','partial','refund_excess']=''
    reason:str=Field(default='',max_length=500)
    expected_version:int=Field(ge=0)
    key:str=Field(min_length=1,max_length=191)


class ManualInitialReceiptBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    unit:Literal['month','quarter','year']
    year:StrictInt=Field(ge=1912,le=9998)
    index:StrictInt=Field(ge=1,le=12)
    amount_ntd:StrictInt=Field(gt=0,le=JS_SAFE_INTEGER_MAX)
    paid_on:date
    handling:Literal['exact','partial','refund_excess']
    reason:str=Field(default='',max_length=500)
    expected_version:StrictInt=Field(ge=0)
    key:str=Field(pattern=r'^[a-z0-9][a-z0-9._:-]{0,190}$')

    @field_validator('amount_ntd',mode='before')
    @classmethod
    def require_lossless_amount(cls,value):
        if type(value) is int and value>JS_SAFE_INTEGER_MAX:
            raise PydanticCustomError('subsidy_period_manual_numeric_unrepresentable',
                '此瀏覽器流程無法準確表示原始實收金額，本次未保存。請保留真實金額，勿為提交而改動金額。')
        return value

    @field_validator('paid_on',mode='before')
    @classmethod
    def require_iso_paid_date(cls,value):
        if not isinstance(value,str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) is None:
            raise ValueError('subsidy_period_manual_initial_date_invalid')
        return value


class ManualInitialReceiptProofView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    receipt_id:int
    period:SubsidyPeriod
    amount_ntd:int
    paid_on:date
    source_label:Literal['人工補登']
    key:str


class ManualInitialReceiptView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    receipt_id:int
    receipt:ManualInitialReceiptProofView
    view:PeriodView

    @model_validator(mode='after')
    def require_lossless_numeric_readback(self):
        # This existing Gov client uses JSON numbers. Fail before commit if its
        # strict safe-integer decoder cannot represent the returned facts.
        def check(value):
            if type(value) is int and abs(value)>JS_SAFE_INTEGER_MAX:
                raise PydanticCustomError('subsidy_period_manual_numeric_unrepresentable',
                    '此瀏覽器流程無法準確表示原始帳務金額，本次未保存。請保留真實金額，勿為提交而改動金額。')
            if isinstance(value,dict):
                for item in value.values():check(item)
            elif isinstance(value,(list,tuple)):
                for item in value:check(item)
        check(self.model_dump())
        return self


@router.post('/manual-initial-receipt',response_model=BaseResponse[ManualInitialReceiptView])
def manual_initial_receipt(body:ManualInitialReceiptBody,principal=Depends(require_system_admin),application=Depends(get_application)):
    if type(principal.id) is not int or principal.id <= 0:
        raise typed_http_error(403,'forbidden','subsidy_period_manual_actor_required','需要已登入的內部使用者身分。','subsidy-period')
    try:
        command=ManualInitialPeriodReceipt(SubsidyPeriod(body.unit,body.year,body.index),body.amount_ntd,body.paid_on,
            body.handling,body.reason.strip(),body.expected_version,body.key,admin_actor_context(principal).actor_id)
        def readback(receipt,view):
            return BaseResponse(data=ManualInitialReceiptView(receipt_id=receipt.receipt_id,
                receipt=ManualInitialReceiptProofView(**asdict(receipt)),view=PeriodView(**_period_payload(view))))
        return _mutate(lambda:application.manual_initial(command,readback=readback))
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error
    except ValueError as error:
        if isinstance(error,ValidationError) and any(item['type']=='subsidy_period_manual_numeric_unrepresentable' for item in error.errors()):
            raise typed_http_error(422,'validation','subsidy_period_manual_numeric_unrepresentable',
                '此瀏覽器流程無法準確表示原始帳務金額，本次未保存。請保留真實金額，勿為提交而改動金額。','subsidy-period') from None
        raise typed_http_error(422,'validation','subsidy_period_manual_initial_invalid','請確認首次政府實收的期間、金額、日期及處置。','subsidy-period') from error
    except MySQLError:
        raise typed_http_error(503,'unavailable','transaction_failed','尚未確認儲存結果，請以原次操作查回。','subsidy-period',retryable=True) from None


@router.post('/differences',response_model=BaseResponse[PeriodView])
def apply_difference(body:DifferenceBody,principal=Depends(require_system_admin),application=Depends(get_application)):
    try:
        view=_mutate(lambda:application.difference(GovernmentDifferenceCommand(SubsidyPeriod(body.unit,body.year,body.index),body.action,
            body.identity,body.amount_ntd,body.bank_row_id,body.handling,body.reason,body.expected_version,body.key,admin_actor_context(principal).actor_id)))
        return BaseResponse(data=_period_payload(view))
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error
    except ValueError as error:
        raise typed_http_error(422,'validation','subsidy_period_invalid','請確認期間、處理方式及金額。','subsidy-period') from error


@router.get('/bank-rows',response_model=BaseResponse[BankPageView])
def bank_rows(principal=Depends(require_system_admin),application=Depends(get_application)):
    return BaseResponse(data={'items':application.bank_rows()})


@router.get('/cases/{case_no}',response_model=BaseResponse[CaseCoverageView])
def case_coverage(case_no: str,principal=Depends(require_system_admin),application=Depends(get_application)):
    if not 1<=len(case_no)<=50:
        raise typed_http_error(422,'validation','case_no_invalid','案件編號格式錯誤。','subsidy-period')
    try:
        return BaseResponse(data=application.case_coverage(case_no))
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error


@router.post('/reconcile',response_model=BaseResponse[ReceiptView])
def reconcile(body: PeriodBody,principal=Depends(require_system_admin),application=Depends(get_application)):
    try:
        identity = _mutate(lambda: application.reconcile(SubsidyPeriod(body.unit,body.year,body.index),body.bank_row_id,
            body.expected_version,body.idempotency_key,admin_actor_context(principal).actor_id))
        return BaseResponse(data={'receipt_id':identity})
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error
    except ValueError as error:
        raise typed_http_error(422,'validation','subsidy_period_invalid','請選擇有效的期間。','subsidy-period') from error


@router.post('/reverse',response_model=BaseResponse[ReceiptView])
def reverse(body: ReversalBody,principal=Depends(require_system_admin),application=Depends(get_application)):
    try:
        identity = _mutate(lambda: application.reverse(body.receipt_id,body.bank_row_id,body.idempotency_key,admin_actor_context(principal).actor_id))
        return BaseResponse(data={'receipt_id':identity})
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error

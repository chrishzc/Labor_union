"""Whole-period reconciliation; no provider sends or application/approval operations."""
from dataclasses import asdict
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import IntegrityError, OperationalError
from api.dependencies.admin_auth import admin_actor_context, require_system_admin
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from domains.government_subsidy.period_reconciliation import PeriodReconciliationConflict, SubsidyPeriod
from domains.government_subsidy.period_reconciliation import SubsidyPeriodLine
from infrastructure.mysql.government_subsidy_period_repository import MySqlGovernmentSubsidyPeriodRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.government_subsidy.period_reconciliation import PeriodReconciliationApplication

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
        data = asdict(view)
        data['label'] = view.period.label
        for coverage,item in zip(view.coverage,data['coverage']):
            item['label'] = coverage.period.label
        return BaseResponse(data=data)
    except PeriodReconciliationConflict as error:
        raise _conflict(error) from error
    except ValueError as error:
        raise typed_http_error(422,'validation','subsidy_period_invalid','請選擇有效的月份、季度或年度。','subsidy-period') from error


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

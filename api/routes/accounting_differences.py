"""Typed owner commands for noncash processing and system amount corrections."""
from datetime import date
from typing import Any, Literal
from fastapi import APIRouter,Depends
from pydantic import BaseModel,ConfigDict,Field
from pymysql.err import IntegrityError,OperationalError
from api.dependencies.admin_auth import require_admin,require_system_admin,admin_actor_context
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.client_difference_repository import MySqlClientDifferenceRepository
from infrastructure.mysql.payroll_amount_correction_repository import MySqlPayrollAmountRepository
from infrastructure.mysql.staff_recovery_disposition_repository import MySqlStaffRecoveryDispositionRepository
from subsystems.client_finance.difference_resolution import ClientDifferenceApplication,ClientDifferenceCommand,ClientDifferenceView
from subsystems.payroll.amount_correction import HistoricalUnpaidPayableCommand,PayrollAmountApplication,PayrollAmountCommand,PayrollAmountView
from subsystems.staff_payables.recovery_disposition import StaffRecoveryDispositionApplication,StaffRecoveryDispositionCommand,StaffRecoveryDispositionView

router=APIRouter(prefix='/api/v1/orders/{case_no}',tags=['Accounting Differences'])


def get_client_application():
    connection=get_connection()
    try:
        yield ClientDifferenceApplication(MySqlClientDifferenceRepository(connection),lambda:MySqlUnitOfWork(connection))
    finally:
        connection.close()


def get_payroll_application():
    connection=get_connection()
    try:
        yield PayrollAmountApplication(MySqlPayrollAmountRepository(connection),lambda:MySqlUnitOfWork(connection))
    finally:
        connection.close()


def get_staff_application():
    connection=get_connection()
    try:
        yield StaffRecoveryDispositionApplication(MySqlStaffRecoveryDispositionRepository(connection),lambda:MySqlUnitOfWork(connection))
    finally:
        connection.close()


class DifferenceBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identity:str=Field(min_length=1,max_length=191)
    action:Literal['loss','reduce_service_fee','union_bank_fee','absorb_overpayment','close_refund','manual_amount','adopt_calculation','settle_direct','recognize_diff']
    amount_ntd:int|None=Field(default=None,ge=0,le=9999999999)
    reason:str=Field(default='',max_length=500)
    expected_version:int=Field(ge=0)
    key:str=Field(min_length=1,max_length=191)


class HistoricalUnpaidPayableBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    staff_id: int = Field(gt=0)
    obligation_identity: str | None = Field(default=None, min_length=1, max_length=191)
    expected_event_id: int | None = Field(default=None, gt=0)
    amount_ntd: int = Field(gt=0, le=9999999999, strict=True)
    due_date: date | None = None
    evidence: str = Field(min_length=1, max_length=500)
    confirmed_unpaid: Literal[True]
    key: str = Field(min_length=1, max_length=100)


def _call(action):
    try:
        return BaseResponse(data=action())
    except ValueError as error:
        raise typed_http_error(409,'conflict',str(error),'款項或計算資料已變動，或處理方式不適用。請重新查詢並核對金額與說明。','accounting-difference') from error
    except (IntegrityError,OperationalError) as error:
        if error.args and error.args[0] in (1062,1205,1213):
            raise typed_http_error(409,'conflict','accounting_difference_write_conflict','資料已由其他操作更新，請重新查詢。','accounting-difference') from error
        raise


@router.get('/client-finance/differences',response_model=BaseResponse[ClientDifferenceView])
def client_query(case_no:str,principal=Depends(require_admin),application=Depends(get_client_application)):
    return _call(lambda:application.query(case_no))


@router.post('/client-finance/differences',response_model=BaseResponse[ClientDifferenceView])
def client_apply(case_no:str,body:DifferenceBody,principal=Depends(require_system_admin),application=Depends(get_client_application)):
    action = body.action
    reason = body.reason.strip()
    if action == 'settle_direct':
        action = 'reduce_service_fee'
        if not reason:
            reason = '人員確認直接銷帳'
    elif action == 'recognize_diff':
        action = 'loss'
        if not reason:
            reason = '人員確認認列差額'
    elif not reason and action in ('loss','reduce_service_fee','union_bank_fee','absorb_overpayment'):
        reason = '人員確認差額處置'
    return _call(lambda:application.apply(ClientDifferenceCommand(case_no,body.identity,action,body.amount_ntd,reason,body.expected_version,body.key,admin_actor_context(principal).actor_id)))


@router.get('/payroll/amount-corrections',response_model=BaseResponse[PayrollAmountView])
def payroll_query(case_no:str,principal=Depends(require_admin),application=Depends(get_payroll_application)):
    return _call(lambda:application.query(case_no))


@router.post('/payroll/amount-corrections',response_model=BaseResponse[PayrollAmountView])
def payroll_apply(case_no:str,body:DifferenceBody,principal=Depends(require_system_admin),application=Depends(get_payroll_application)):
    return _call(lambda:application.apply(PayrollAmountCommand(case_no,body.identity,body.action,body.amount_ntd,body.reason,body.expected_version,body.key,admin_actor_context(principal).actor_id)))


@router.post('/payroll/historical-unpaid-payable', response_model=BaseResponse[str])
def record_historical_unpaid_payable(
    case_no: str, body: HistoricalUnpaidPayableBody,
    principal=Depends(require_system_admin), application=Depends(get_payroll_application),
):
    return _call(lambda: application.record_historical_unpaid(HistoricalUnpaidPayableCommand(
        case_no, body.staff_id, body.obligation_identity, body.expected_event_id,
        body.amount_ntd, body.due_date, body.evidence, body.key, admin_actor_context(principal).actor_id,
    )))


@router.post('/payroll/sync-historical-baseline-obligations', response_model=BaseResponse[dict[str, Any]])
def sync_historical_baseline_obligations_route(
    case_no: str,
    principal=Depends(require_admin),
):
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.payroll.historical_baseline_obligation_sync import (
        sync_historical_staff_baseline_obligations,
    )
    conn = get_connection()
    try:
        result = sync_historical_staff_baseline_obligations(conn, case_no, actor=admin_actor_context(principal))
        conn.commit()
        return BaseResponse(data=result)
    finally:
        conn.close()


@router.get('/staff-payables/recovery-dispositions',response_model=BaseResponse[StaffRecoveryDispositionView])
def staff_query(case_no:str,principal=Depends(require_admin),application=Depends(get_staff_application)):
    return _call(lambda:application.query(case_no))


@router.post('/staff-payables/recovery-dispositions',response_model=BaseResponse[StaffRecoveryDispositionView])
def staff_apply(case_no:str,body:DifferenceBody,principal=Depends(require_system_admin),application=Depends(get_staff_application)):
    action = body.action
    reason = body.reason.strip()
    if action == 'settle_direct':
        action = 'absorb_overpayment'
        if not reason:
            reason = '人員確認直接銷帳'
    elif action == 'recognize_diff':
        action = 'loss'
        if not reason:
            reason = '人員確認認列差額'
    elif not reason:
        reason = '人員確認差額處置'
    return _call(lambda:application.apply(StaffRecoveryDispositionCommand(case_no,body.identity,action,body.amount_ntd or 0,reason,body.expected_version,body.key,admin_actor_context(principal).actor_id)))

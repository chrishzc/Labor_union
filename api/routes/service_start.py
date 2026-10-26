"""Staff results and capability-scoped union substitute actions; no provider execution."""

from dataclasses import asdict
from fastapi import APIRouter, Depends, Query
from api.dependencies.admin_auth import require_line_matching_override
from api.dependencies.service_start import get_service_start_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.service_start import ServiceStartCommand, ServiceStartInquiry, ServiceStartDates, ServiceStartPage, ServiceStartView
from domains.scheduling.service_start import ServiceStartConflict
from domains.scheduling.leave_result import LeaveDateChange
from api.schemas.service_start import LeaveDeferDates, HandoverContext, HandoverInquiry

router=APIRouter(prefix='/api/v1/scheduling/service-start',tags=['Service Start'])


def call(operation):
    try:
        return operation()
    except ServiceStartConflict as error:
        raise typed_http_error(409,'conflict',error.code,error.message,'service-start') from error
    except (ValueError, LookupError) as error:
        raise typed_http_error(409,'domain_blocked',str(error),'目前資料無法完成安排，請重新查詢並核對。','service-start') from error
    except Exception as error:
        if hasattr(error,'error'):
            detail=error.error
            response=typed_http_error(409,'conflict',detail.code,detail.message,'service-start')
            response.detail['error']['domain_blockers']=list(detail.domain_blockers)
            raise response from error
        raise


@router.get('/todos',response_model=BaseResponse[ServiceStartPage])
def todos(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),case_no:str|None=Query(None,max_length=50),
          principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    items,total=call(lambda:app.todos(page,page_size,case_no))
    return BaseResponse(data={'items':[asdict(item) for item in items],'total':total,'page':page,'page_size':page_size})


@router.get('/staff-options')
def staff_options(keyword:str=Query('',max_length=50),principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data={'items':app.repository.staff_options(keyword)})


@router.get('/handover/context',response_model=BaseResponse[HandoverContext])
def handover_context(case_no:str=Query(...,min_length=1,max_length=50),assignment_id:int|None=Query(None,gt=0),
        principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.handover_context(case_no,assignment_id))))


@router.post('/handover/inquire',response_model=BaseResponse[ServiceStartView])
def handover_inquire(body:HandoverInquiry,principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.inquire_handover(body.case_no,body.assignment_id,body.staff_id,
        body.expected_order_version,body.expected_scheduling_version,str(principal.username),body.idempotency_key))))


@router.get('/{request_id}',response_model=BaseResponse[ServiceStartView])
def detail(request_id:int,principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.repository.view(request_id))))


@router.post('/{request_id}/inquire',response_model=BaseResponse[ServiceStartView])
def inquire(request_id:int,body:ServiceStartInquiry,principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.inquire(request_id,body.staff_id,body.start_date,body.end_date,
        body.expected_version,str(principal.username),body.idempotency_key))))


@router.post('/{request_id}/invite',response_model=BaseResponse[ServiceStartView])
def invite(request_id:int,body:ServiceStartCommand,principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.invite(request_id,body.expected_version,str(principal.username),body.idempotency_key))))


@router.post('/{request_id}/dates',response_model=BaseResponse[ServiceStartView])
def dates(request_id:int,body:ServiceStartDates,principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.save_dates(request_id,body.start_date,body.expected_version,str(principal.username),body.idempotency_key,
        tuple(LeaveDateChange(d.original_date,d.new_date) for d in body.date_changes) if body.date_changes is not None else None))))


@router.post('/{request_id}/defer',response_model=BaseResponse[ServiceStartView])
def defer(request_id:int,body:LeaveDeferDates,principal=Depends(require_line_matching_override),app=Depends(get_service_start_application)):
    return BaseResponse(data=asdict(call(lambda:app.save_defer_dates(request_id,
        tuple(LeaveDateChange(d.original_date,d.new_date) for d in body.dates),
        body.expected_version,str(principal.username),body.idempotency_key))))

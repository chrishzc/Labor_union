"""
File: line_order_groups.py
Description: 提供具管理員授權的 LINE 訂單群組 compatibility 與 numbered 唯讀 API。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_order_group_reader,
)
from api.dependencies.line_runtime import get_line_order_group_query_application
from api.schemas.line_order_groups import (
    LineOrderGroupEventPageResponse,
    LineOrderGroupEventResponse,
    LineOrderGroupNumberedPageResponse,
    LineOrderGroupPageResponse,
    LineOrderGroupRecord,
    LineOrderGroupWorkspacePageResponse,
    LineOrderGroupWorkspaceRecordResponse,
    LineOrderGroupWorkspaceEventPageResponse,
)
from domains.line.order_group import LineOrderGroupBindingStatus
from subsystems.access.authentication_session import AdminPrincipal
from datetime import date
from dataclasses import asdict
from pydantic import BaseModel, ConfigDict, Field
from api.dependencies.admin_auth import require_customer_service_handler
from api.dependencies.service_day_log_reminders import get_service_day_log_reminders
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from subsystems.line.service_day_log_reminders import SendServiceDayLogReminder

router = APIRouter(prefix="/api/v1/line/order-groups", tags=["LINE Order Groups"])


class LogReminderSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    missing_from: date
    missing_through: date
    idempotency_key: str = Field(min_length=1, max_length=100)


class LogReminderItem(BaseModel):
    case_no: str
    staff_id: int
    missing_from: date
    missing_through: date
    consecutive_days: int
    group_label: str
    can_send: bool


class LogReminderPage(BaseModel):
    items: list[LogReminderItem]
    total: int
    page: int
    page_size: int


class LogReminderReceipt(BaseModel):
    task_id: int
    status: str


@router.get("/log-reminders", response_model=BaseResponse[LogReminderPage])
def list_log_reminders(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                       principal: AdminPrincipal = Depends(require_line_order_group_reader),
                       application=Depends(get_service_day_log_reminders)):
    items, total = application.list(page, page_size)
    return BaseResponse(data={"items": [{**asdict(item.gap), "group_label": item.group_label,
                                         "can_send": item.can_send} for item in items],
                              "total": total, "page": page, "page_size": page_size})


@router.post("/log-reminders/send", response_model=BaseResponse[LogReminderReceipt])
def send_log_reminder(body: LogReminderSendRequest,
                      principal: AdminPrincipal = Depends(require_customer_service_handler),
                      application=Depends(get_service_day_log_reminders)):
    try:
        result = application.send(SendServiceDayLogReminder(**body.model_dump()))
    except (ValueError, RuntimeError) as error:
        if str(error) not in {"service_day_log_reminder_date_invalid", "service_day_log_reminder_no_longer_applicable",
                              "line_delivery_idempotency_conflict"}:
            raise
        raise typed_http_error(409, "conflict", str(error),
                               "缺漏或案件群組已更新，請重新整理後再操作。", "service-day-log-reminder") from error
    return BaseResponse(data={"task_id": result.task_id.value, "status": result.status.value})


@router.get("", response_model=LineOrderGroupPageResponse)
def list_order_groups(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    page = get_line_order_group_query_application().list(
        admin_actor_context(principal),
        status=status,
        limit=limit,
    )
    return LineOrderGroupPageResponse(
        items=[_record(item) for item in page.items], total=page.total
    )


@router.get("/numbered", response_model=LineOrderGroupNumberedPageResponse)
def list_order_groups_numbered(
    status: LineOrderGroupBindingStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    result = get_line_order_group_query_application().list_numbered(
        admin_actor_context(principal),
        status=status.value if status else None,
        page=page,
        page_size=page_size,
    )
    return LineOrderGroupNumberedPageResponse(
        items=[_record(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
    )


@router.get("/workspace/numbered", response_model=LineOrderGroupWorkspacePageResponse)
def list_order_group_workspace(
    search: str | None = Query(default=None, max_length=50),
    status: LineOrderGroupBindingStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    result = get_line_order_group_query_application().workspace_list(
        admin_actor_context(principal), search=search.strip() or None if search else None,
        status=status.value if status else None, page=page, page_size=page_size,
    )
    return LineOrderGroupWorkspacePageResponse.model_validate(result)


@router.get("/workspace/{case_no}", response_model=LineOrderGroupWorkspaceRecordResponse)
def get_order_group_workspace(
    case_no: str = Path(min_length=1, max_length=50, pattern=r"^\S(?:.*\S)?$"),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    result = get_line_order_group_query_application().workspace_get(admin_actor_context(principal), case_no)
    if result is None:
        raise HTTPException(status_code=404, detail="找不到案件的服務群組")
    return LineOrderGroupWorkspaceRecordResponse.model_validate(result)


@router.get("/workspace/{case_no}/events/numbered", response_model=LineOrderGroupWorkspaceEventPageResponse)
def get_order_group_workspace_events(
    case_no: str = Path(min_length=1, max_length=50, pattern=r"^\S(?:.*\S)?$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    result = get_line_order_group_query_application().workspace_events(
        admin_actor_context(principal), case_no, page=page, page_size=page_size,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="找不到案件的服務群組")
    return LineOrderGroupWorkspaceEventPageResponse.model_validate(result)


@router.get("/{case_no}", response_model=LineOrderGroupRecord)
def get_order_group(
    case_no: str,
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    result = get_line_order_group_query_application().get(
        admin_actor_context(principal),
        case_no,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="找不到訂單群組綁定")
    return _record(result)


@router.get("/{case_no}/events", response_model=list[LineOrderGroupEventResponse])
def get_order_group_events(
    case_no: str,
    limit: int = Query(default=100, ge=1, le=200),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    events = get_line_order_group_query_application().events(
        admin_actor_context(principal),
        case_no,
        limit=limit,
    )
    return [
        LineOrderGroupEventResponse(
            event_id=event.event_id,
            case_no=event.case_no,
            event_type=event.event_type,
            actor_id=event.actor_id,
            occurred_at=event.occurred_at,
            invitation_fingerprint=event.invitation_fingerprint,
        )
        for event in events
    ]


@router.get(
    "/{case_no}/events/numbered",
    response_model=LineOrderGroupEventPageResponse,
)
def get_order_group_events_numbered(
    case_no: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    principal: AdminPrincipal = Depends(require_line_order_group_reader),
):
    result = get_line_order_group_query_application().events_numbered(
        admin_actor_context(principal),
        case_no,
        page=page,
        page_size=page_size,
    )
    return LineOrderGroupEventPageResponse(
        items=[
            LineOrderGroupEventResponse(
                event_id=event.event_id,
                case_no=event.case_no,
                event_type=event.event_type,
                actor_id=event.actor_id,
                occurred_at=event.occurred_at,
                invitation_fingerprint=event.invitation_fingerprint,
            )
            for event in result.items
        ],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
    )


def _record(snapshot) -> LineOrderGroupRecord:
    return LineOrderGroupRecord(
        case_no=snapshot.case_no,
        group_id=snapshot.group_id.value if snapshot.group_id else None,
        status=snapshot.status.value,
        version=snapshot.version.value,
    )


__all__ = ["router"]

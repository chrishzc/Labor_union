"""
File: line_order_groups.py
Description: 提供具管理員授權的 LINE 訂單群組 compatibility 與 numbered 唯讀 API。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

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
)
from domains.line.order_group import LineOrderGroupBindingStatus
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/line/order-groups", tags=["LINE Order Groups"])


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

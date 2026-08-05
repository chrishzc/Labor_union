"""LINE customer service ticket management API."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import require_line_agent
from api.schemas.base import BaseResponse
from api.schemas.customer_service_tickets import (
    ClientProfileFieldUpdateRequest,
    TicketReplyRequest,
    TicketUpdateRequest,
)
from line.worker import wake_worker
from services.admin_auth_service import AdminPrincipal
from services.customer_service_ticket_service import (
    CustomerServiceTicketNotFoundError,
    CustomerServiceTicketStateError,
    apply_client_profile_field_update,
    get_ticket,
    get_ticket_summary,
    list_tickets,
    reply_ticket,
    update_ticket,
)


router = APIRouter(
    prefix="/api/v1/line/customer-service/tickets",
    tags=["LINE Customer Service"],
    dependencies=[Depends(require_line_agent)],
)


def _raise_ticket_error(exc: Exception) -> NoReturn:
    if isinstance(exc, CustomerServiceTicketNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, CustomerServiceTicketStateError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/summary", response_model=BaseResponse[dict])
def ticket_summary():
    return BaseResponse(data=get_ticket_summary())


@router.get("", response_model=BaseResponse[dict])
def ticket_list(
    status: str | None = "waiting",
    category: str | None = None,
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    try:
        result = list_tickets(
            status=status,
            category=category,
            search=search,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise_ticket_error(exc)
    return BaseResponse(data=result)


@router.get("/{ticket_id}", response_model=BaseResponse[dict])
def ticket_detail(ticket_id: int):
    try:
        result = get_ticket(ticket_id)
    except CustomerServiceTicketNotFoundError as exc:
        _raise_ticket_error(exc)
    return BaseResponse(data=result)


@router.patch("/{ticket_id}", response_model=BaseResponse[dict])
def ticket_update(
    ticket_id: int,
    payload: TicketUpdateRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_agent),
):
    try:
        result = update_ticket(
            ticket_id,
            status=payload.status,
            internal_note=payload.internal_note,
            admin_user_id=principal.id,
        )
    except (CustomerServiceTicketNotFoundError, ValueError) as exc:
        _raise_ticket_error(exc)
    request.state.audit_action = "line.customer_service.update"
    request.state.audit_resource_type = "customer_service_ticket"
    request.state.audit_resource_id = str(ticket_id)
    request.state.audit_details = {"status": payload.status}
    return BaseResponse(data=result, message="客服需求已更新")


@router.post("/{ticket_id}/reply", response_model=BaseResponse[dict])
def ticket_reply(
    ticket_id: int,
    payload: TicketReplyRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_agent),
):
    try:
        result = reply_ticket(
            ticket_id,
            reply_text=payload.reply_text,
            internal_note=payload.internal_note,
            resolve=payload.resolve,
            admin_user_id=principal.id,
        )
    except (CustomerServiceTicketNotFoundError, CustomerServiceTicketStateError, ValueError) as exc:
        _raise_ticket_error(exc)
    request.state.audit_action = "line.customer_service.reply"
    request.state.audit_resource_type = "customer_service_ticket"
    request.state.audit_resource_id = str(ticket_id)
    request.state.audit_details = {"resolve": payload.resolve}
    wake_worker()
    return BaseResponse(data=result, message="已排入 LINE 回覆")


@router.post("/{ticket_id}/client-profile-field", response_model=BaseResponse[dict])
def ticket_client_profile_field_update(
    ticket_id: int,
    payload: ClientProfileFieldUpdateRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_agent),
):
    try:
        result = apply_client_profile_field_update(
            ticket_id,
            field=payload.field,
            action=payload.action,
            value=payload.value,
            note=payload.note,
            admin_user_id=principal.id,
        )
    except (CustomerServiceTicketNotFoundError, ValueError) as exc:
        _raise_ticket_error(exc)
    request.state.audit_action = "line.customer_service.client_profile_update"
    request.state.audit_resource_type = "customer_service_ticket"
    request.state.audit_resource_id = str(ticket_id)
    request.state.audit_details = {"field": payload.field, "action": payload.action}
    return BaseResponse(data=result, message="客戶資料已更新")

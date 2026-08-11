"""Capability-protected Customer Service API."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import admin_actor_context, require_customer_service_handler, require_customer_service_reader
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.schemas.base import BaseResponse
from api.schemas.customer_service import (
    CustomerServiceDetailView, CustomerServicePageView, CustomerServiceReplyRequest,
    CustomerServiceSummaryView, CustomerServiceUpdateRequest,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus, CustomerServiceTransitionError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.customer_service.application import (
    CustomerServiceApplication, CustomerServiceTicketNotFoundError, CustomerServiceVersionConflictError,
)
from subsystems.customer_service.contracts import CustomerServiceListQuery, ReplyCustomerServiceTicket, UpdateCustomerServiceTicket


router = APIRouter(prefix="/api/v1/customer-service/tickets", tags=["Customer Service"])


def _application():
    return CustomerServiceApplication(open_line_unit_of_work)


@router.get("/summary", response_model=BaseResponse[CustomerServiceSummaryView])
def summary(_: AdminPrincipal = Depends(require_customer_service_reader)):
    return BaseResponse(data=_application().summary())


@router.get("", response_model=BaseResponse[CustomerServicePageView])
def list_tickets(
    status: CustomerServiceStatus | None = CustomerServiceStatus.WAITING,
    category: CustomerServiceCategory | None = None, search: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    _: AdminPrincipal = Depends(require_customer_service_reader),
):
    return BaseResponse(data=_application().list(CustomerServiceListQuery(status, category, search, page, page_size)))


@router.get("/{ticket_id}", response_model=BaseResponse[CustomerServiceDetailView])
def detail(ticket_id: int, _: AdminPrincipal = Depends(require_customer_service_reader)):
    return BaseResponse(data=_call(_application().detail, ticket_id))


@router.patch("/{ticket_id}", response_model=BaseResponse[CustomerServiceDetailView])
def update(ticket_id: int, payload: CustomerServiceUpdateRequest, request: Request, principal: AdminPrincipal = Depends(require_customer_service_handler)):
    actor = admin_actor_context(principal).actor_id
    command = UpdateCustomerServiceTicket(ticket_id, payload.status, payload.internal_note, ExpectedVersion(payload.expected_version), actor, IdempotencyKey(payload.idempotency_key), _correlation("update"))
    result = _call(_application().update, command)
    _audit_request(request, "update", ticket_id)
    return BaseResponse(data=result, message="客服需求已更新")


@router.post("/{ticket_id}/reply", response_model=BaseResponse[CustomerServiceDetailView])
def reply(ticket_id: int, payload: CustomerServiceReplyRequest, request: Request, principal: AdminPrincipal = Depends(require_customer_service_handler)):
    actor = admin_actor_context(principal).actor_id
    command = ReplyCustomerServiceTicket(ticket_id, payload.reply_text, payload.resolve, payload.internal_note, ExpectedVersion(payload.expected_version), actor, principal.id, IdempotencyKey(payload.idempotency_key), _correlation("reply"))
    result = _call(_application().reply, command)
    _audit_request(request, "reply", ticket_id)
    publish_line_wakeup_best_effort()
    return BaseResponse(data=result, message="已排入 LINE 回覆")


def _call(operation, *arguments):
    try:
        return operation(*arguments)
    except CustomerServiceTicketNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "customer_service_ticket_not_found", "message": str(error)}) from error
    except (CustomerServiceVersionConflictError, CustomerServiceTransitionError) as error:
        raise HTTPException(status_code=409, detail={"code": "customer_service_ticket_version_conflict", "message": str(error)}) from error


def _correlation(operation):
    return CorrelationId(f"customer-service:{operation}:{uuid4()}")


def _audit_request(request, operation, ticket_id):
    request.state.audit_action = f"customer_service.ticket.{operation}"
    request.state.audit_resource_type = "customer_service_ticket"
    request.state.audit_resource_id = str(ticket_id)


__all__ = ["router"]

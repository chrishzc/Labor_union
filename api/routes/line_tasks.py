"""
File: line_tasks.py
Description: 提供 LINE Delivery 的 canonical 查詢與既有控制端點。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_task_controller,
    require_line_task_reader,
)
from api.dependencies.line_runtime import (
    get_line_delivery_task_admin_application,
    get_line_wakeup_publisher,
)
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.line_tasks import (
    LineDeliveryPublicAttemptView,
    LineDeliveryPublicDetailView,
    LineDeliveryPublicItemView,
    LineDeliveryPublicPageView,
    LineDeliveryPublicSourceType,
    LineDeliveryPublicSummaryView,
    LineDeliveryTaskActionResultView,
    LineTaskActionRequest,
)
from domains.line.delivery import LineDeliveryStatus, LineDeliveryTaskSnapshot
from domains.line.identities import LineDeliveryTaskId
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.delivery_admin_application import (
    LineDeliveryTaskNotFoundError,
    LineDeliveryTaskStateConflictError,
)
from subsystems.line.delivery_admin_contracts import (
    ControlLineDeliveryTaskCommand,
    LineDeliveryAdminQuery,
)
from subsystems.line.runtime_health import classify_line_worker_health

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/line/tasks", tags=["LINE Tasks"])

_PUBLIC_QUERY_ERROR_RESPONSES = {
    401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證。"},
    403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權讀取 LINE 發送任務。"},
    422: {"model": GlobalTypedErrorResponseView, "description": "查詢欄位不符合公開契約。"},
    503: {"model": GlobalTypedErrorResponseView, "description": "LINE 發送任務查詢暫時無法完成。"},
}


def _raise_task_error(exc: Exception) -> NoReturn:
    if isinstance(exc, LineDeliveryTaskNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, LineDeliveryTaskStateConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get(
    "/summary",
    response_model=BaseResponse[LineDeliveryPublicSummaryView],
    responses=_PUBLIC_QUERY_ERROR_RESPONSES,
)
def task_summary(
    principal: AdminPrincipal = Depends(require_line_task_reader),
):
    try:
        summary = get_line_delivery_task_admin_application().summary(
            admin_actor_context(principal)
        )
    except HTTPException:
        raise
    except Exception as error:
        _raise_query_error(503, "line_delivery_query_unavailable", "LINE 發送任務查詢暫時無法完成。")
    worker = _worker_health()
    summary["worker_running"] = worker["running"]
    summary["worker_status"] = worker["status"]
    try:
        data = LineDeliveryPublicSummaryView.model_validate(summary)
    except Exception as error:
        _raise_query_error(
            503,
            "line_delivery_query_invalid_result",
            "LINE 發送任務查詢結果無法驗證。",
            retryable=False,
        )
    return BaseResponse[LineDeliveryPublicSummaryView](data=data)


@router.get(
    "",
    response_model=BaseResponse[LineDeliveryPublicPageView],
    responses=_PUBLIC_QUERY_ERROR_RESPONSES,
)
def task_list(
    request: Request,
    status: LineDeliveryStatus | None = None,
    source_type: LineDeliveryPublicSourceType | None = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_line_task_reader),
):
    _reject_unsupported_query_params(request)
    try:
        result = get_line_delivery_task_admin_application().list(
            LineDeliveryAdminQuery(
                statuses=(status,) if status else (),
                source_aggregate_types=_source_aggregate_types(source_type),
                scheduled_from=scheduled_from,
                scheduled_to=scheduled_to,
                page=page,
                page_size=page_size,
            ),
            admin_actor_context(principal),
        )
    except HTTPException:
        raise
    except ValueError as error:
        _raise_query_error(
            503,
            "line_delivery_query_invalid_result",
            "LINE 發送任務查詢結果無法驗證。",
            retryable=False,
        )
    except Exception as error:
        _raise_query_error(503, "line_delivery_query_unavailable", "LINE 發送任務查詢暫時無法完成。")
    try:
        data = LineDeliveryPublicPageView(
            items=[_public_item(item) for item in result.items],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            total_pages=max(1, (result.total + result.page_size - 1) // result.page_size),
        )
    except Exception as error:
        _raise_query_error(
            503,
            "line_delivery_query_invalid_result",
            "LINE 發送任務查詢結果無法驗證。",
            retryable=False,
        )
    return BaseResponse[LineDeliveryPublicPageView](data=data)


@router.get(
    "/{task_id}",
    response_model=BaseResponse[LineDeliveryPublicDetailView],
    responses={
        **_PUBLIC_QUERY_ERROR_RESPONSES,
        404: {"model": GlobalTypedErrorResponseView, "description": "找不到 LINE 發送任務。"},
    },
)
def task_detail(
    task_id: int,
    principal: AdminPrincipal = Depends(require_line_task_reader),
):
    try:
        task, attempts = get_line_delivery_task_admin_application().get(
            LineDeliveryTaskId(task_id),
            admin_actor_context(principal),
        )
    except LineDeliveryTaskNotFoundError as exc:
        _raise_query_error(404, "line_delivery_task_not_found", "找不到 LINE 發送任務。")
    except HTTPException:
        raise
    except Exception as error:
        _raise_query_error(503, "line_delivery_query_unavailable", "LINE 發送任務查詢暫時無法完成。")
    try:
        data = LineDeliveryPublicDetailView(
            task=_public_item(task),
            attempts=[_public_attempt(item) for item in attempts],
        )
    except Exception as error:
        _raise_query_error(
            503,
            "line_delivery_query_invalid_result",
            "LINE 發送任務查詢結果無法驗證。",
            retryable=False,
        )
    return BaseResponse[LineDeliveryPublicDetailView](data=data)


_SOURCE_TYPE_GROUPS = {
    LineDeliveryPublicSourceType.GENERAL_PUSH: (
        "line_push",
        "customer_service_ticket",
        "contract_document_version",
        "line_follow_schedule",
        "line_identity",
        "line_review_request",
        "line_webhook_event",
        "line_order_group_invitation",
        "runtime_health_event",
        "matching_notification_intent",
        "matching_response_event",
        "matching_willingness_card",
        "candidate_matching_willingness_card",
        "order",
        "client_finance_account",
        "case_staff_assignment",
    ),
    LineDeliveryPublicSourceType.CUSTOMER_SERVICE: ("customer_service_ticket",),
    LineDeliveryPublicSourceType.CONTRACT: ("contract_document_version",),
    LineDeliveryPublicSourceType.FOLLOW_SCHEDULE: ("line_follow_schedule",),
    LineDeliveryPublicSourceType.IDENTITY: (
        "line_identity",
        "provisional_registration",
    ),
    LineDeliveryPublicSourceType.IDENTITY_REVIEW: ("line_review_request",),
    LineDeliveryPublicSourceType.RICH_MENU: ("rich_menu_link", "rich_menu_unlink"),
    LineDeliveryPublicSourceType.RICH_MENU_LINK: ("rich_menu_link",),
    LineDeliveryPublicSourceType.RICH_MENU_UNLINK: ("rich_menu_unlink",),
    LineDeliveryPublicSourceType.WEBHOOK: ("line_webhook_event",),
    LineDeliveryPublicSourceType.GROUP_INVITATION: ("line_order_group_invitation",),
    LineDeliveryPublicSourceType.RUNTIME: ("runtime_health_event",),
    LineDeliveryPublicSourceType.MATCHING: (
        "matching_notification_intent",
        "matching_response_event",
        "matching_willingness_card",
        "candidate_matching_willingness_card",
        "matching_schedule_recipient",
        "matching_schedule_snapshot",
    ),
    LineDeliveryPublicSourceType.ORDER: ("order",),
    LineDeliveryPublicSourceType.FINANCE: ("client_finance_account",),
    LineDeliveryPublicSourceType.ASSIGNMENT: (
        "case_staff_assignment",
        "scheduling_staff_leave_request",
    ),
}
_SOURCE_TYPE_BY_AGGREGATE = {
    aggregate: public_type
    for public_type, aggregates in _SOURCE_TYPE_GROUPS.items()
    for aggregate in aggregates
}
_PUBLIC_ATTEMPT_OUTCOMES = frozenset(
    {"success", "retryable_failure", "terminal_failure"}
)
_ALLOWED_QUERY_PARAMETERS = frozenset(
    {"status", "source_type", "scheduled_from", "scheduled_to", "page", "page_size"}
)


def _source_aggregate_types(
    source_type: LineDeliveryPublicSourceType | None,
) -> tuple[str, ...]:
    return () if source_type is None else _SOURCE_TYPE_GROUPS[source_type]


def _public_source_type(source_aggregate_type: str) -> LineDeliveryPublicSourceType:
    try:
        return _SOURCE_TYPE_BY_AGGREGATE[source_aggregate_type]
    except KeyError as error:
        raise ValueError("LINE delivery source type is not public") from error


def _public_item(item) -> LineDeliveryPublicItemView:
    source_type = _public_source_type(item.source_aggregate_type)
    return LineDeliveryPublicItemView(
        id=item.task_id.value,
        task_id=item.task_id.value,
        task_type=source_type.value,
        source_type=source_type,
        status=item.status,
        scheduled_at=item.scheduled_at,
        completed_attempts=item.completed_attempts,
        max_attempts=item.maximum_attempts,
        next_retry_at=item.next_attempt_at,
        sent_at=item.sent_at,
        failed_at=item.failed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _public_attempt(item) -> LineDeliveryPublicAttemptView:
    if item.outcome not in _PUBLIC_ATTEMPT_OUTCOMES:
        raise ValueError("LINE delivery attempt outcome is not public")
    return LineDeliveryPublicAttemptView(
        attempt_number=item.attempt_number,
        outcome=item.outcome,
        retry_after_seconds=item.retry_after_seconds,
        started_at=item.started_at,
        completed_at=item.completed_at,
    )


def _reject_unsupported_query_params(request: Request) -> None:
    unsupported = sorted(set(request.query_params) - _ALLOWED_QUERY_PARAMETERS)
    if unsupported:
        _raise_query_error(422, "line_delivery_query_filter_not_allowed", "LINE 發送任務查詢篩選條件不在允許範圍。")


def _raise_query_error(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool | None = None,
) -> NoReturn:
    category = {
        403: "forbidden",
        404: "not_found",
        422: "validation",
        503: "unavailable",
    }.get(status_code, "internal")
    raise HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "category": category,
                "code": code,
                "message": message,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": status_code == 503 if retryable is None else retryable,
                "correlation_id": "line-delivery-query",
                "current_version": None,
            }
        },
    )


@router.post(
    "/{task_id}/cancel",
    response_model=BaseResponse[LineDeliveryTaskActionResultView],
)
def cancel_task(
    task_id: int,
    payload: LineTaskActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_task_controller),
):
    task = _control("cancel", task_id, payload, principal)
    _set_task_audit(request, "line.task.cancel", task_id, payload.reason)
    return BaseResponse(data=_task_snapshot(task), message="任務已取消")


@router.post(
    "/{task_id}/run-now",
    response_model=BaseResponse[LineDeliveryTaskActionResultView],
)
def run_task_now(
    task_id: int,
    payload: LineTaskActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_task_controller),
):
    task = _control("run_now", task_id, payload, principal)
    _set_task_audit(request, "line.task.run_now", task_id, payload.reason)
    _publish_wakeup()
    return BaseResponse(data=_task_snapshot(task), message="任務已排入立即執行")


@router.post(
    "/{task_id}/retry",
    response_model=BaseResponse[LineDeliveryTaskActionResultView],
)
def retry_task(
    task_id: int,
    payload: LineTaskActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_task_controller),
):
    task = _control("retry", task_id, payload, principal)
    _set_task_audit(request, "line.task.retry", task_id, payload.reason)
    _publish_wakeup()
    return BaseResponse(data=_task_snapshot(task), message="失敗任務已重新排入")


def _control(action, task_id, payload, principal):
    suffix = uuid4().hex
    command = ControlLineDeliveryTaskCommand(
        LineDeliveryTaskId(task_id),
        admin_actor_context(principal),
        payload.reason.strip() or "管理員執行 LINE 任務操作",
        IdempotencyKey(payload.idempotency_key.strip() or f"line-task:{action}:{suffix}"),
        CorrelationId(payload.correlation_id.strip() or f"line-task:{action}:{suffix}"),
    )
    application = get_line_delivery_task_admin_application()
    try:
        return {
            "cancel": application.cancel,
            "run_now": application.run_now,
            "retry": application.retry,
        }[action](command)
    except (LineDeliveryTaskNotFoundError, LineDeliveryTaskStateConflictError, ValueError) as exc:
        _raise_task_error(exc)


def _task_snapshot(task: LineDeliveryTaskSnapshot) -> LineDeliveryTaskActionResultView:
    return LineDeliveryTaskActionResultView(
        id=task.task_id.value,
        task_id=task.task_id.value,
        task_type=_legacy_task_type(task.request.source_aggregate_type),
        message_kind=task.request.message_kind.value,
        scheduled_at=task.request.scheduled_at,
        status=task.status,
        completed_attempts=task.completed_attempts,
    )


def _admin_record(item) -> dict[str, object]:
    preview = _message_text(item.payload_json)
    return {
        "id": item.task_id.value,
        "task_id": item.task_id.value,
        "task_type": _legacy_task_type(item.source_aggregate_type),
        "to_user_id": item.recipient_identity,
        "recipient_type": item.recipient_type,
        "recipient_identity": item.recipient_identity,
        "message_kind": item.message_kind,
        "message_text": preview,
        "payload_json": item.payload_json,
        "status": item.status.value,
        "scheduled_at": item.scheduled_at,
        "source_aggregate_type": item.source_aggregate_type,
        "source_aggregate_identity": item.source_aggregate_identity,
        "completed_attempts": item.completed_attempts,
        "max_attempts": item.maximum_attempts,
        "next_retry_at": item.next_attempt_at,
        "provider_message_id": item.provider_message_id,
        "error_code": item.error_code,
        "error_message": item.error_message,
        "sent_at": item.sent_at,
        "failed_at": item.failed_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _message_text(payload_json: str) -> str:
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return str(payload_json or "")
    if isinstance(payload, dict):
        for key in ("text", "message", "content"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
    return str(payload_json or "")

def _legacy_task_type(source_type: str) -> str:
    return {
        "rich_menu_link": "rich_menu_link",
        "rich_menu_unlink": "rich_menu_unlink",
    }.get(source_type, "line_push")


def _set_task_audit(request, action, task_id, reason):
    request.state.audit_action = action
    request.state.audit_resource_type = "line_delivery_task"
    request.state.audit_resource_id = str(task_id)
    request.state.audit_details = {"reason": reason.strip()} if reason.strip() else None


def _publish_wakeup() -> None:
    try:
        get_line_wakeup_publisher().publish()
    except Exception:
        LOGGER.exception("LINE worker wake signal failed; durable task remains queued")


def _worker_health() -> dict[str, object]:
    connection = get_connection()
    try:
        heartbeat = MySqlLineRuntimeRepository(connection).latest_heartbeat()
    except Exception:
        return {"status": "unknown", "running": False}
    finally:
        connection.close()
    return classify_line_worker_health(
        heartbeat,
        stale_after_seconds=float(os.getenv("LINE_WORKER_STALE_SECONDS", "90")),
    )


__all__ = ["router"]

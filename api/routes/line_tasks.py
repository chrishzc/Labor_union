"""
================================================================================
檔案名稱: api/routes/line_tasks.py
功能說明: canonical LINE 發送任務管理 API；查詢、取消、立即執行與失敗重送
================================================================================
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
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
from api.schemas.line_tasks import LineTaskActionRequest
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


def _raise_task_error(exc: Exception) -> NoReturn:
    if isinstance(exc, LineDeliveryTaskNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, LineDeliveryTaskStateConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/summary", response_model=BaseResponse[dict])
def task_summary(
    principal: AdminPrincipal = Depends(require_line_task_reader),
):
    summary = get_line_delivery_task_admin_application().summary(
        admin_actor_context(principal)
    )
    worker = _worker_health()
    summary["worker_running"] = worker["running"]
    summary["worker_status"] = worker["status"]
    return BaseResponse(data=summary)


@router.get("", response_model=BaseResponse[dict])
def task_list(
    status: LineDeliveryStatus | None = None,
    task_type: str | None = None,
    user_id: str | None = None,
    onboarding_only: bool = False,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_line_task_reader),
):
    source_type = "line_follow_schedule" if onboarding_only else task_type
    if source_type == "line_push":
        source_type = None
    try:
        result = get_line_delivery_task_admin_application().list(
            LineDeliveryAdminQuery(
                statuses=(status,) if status else (),
                source_aggregate_type=source_type,
                recipient_identity=user_id,
                scheduled_from=scheduled_from,
                scheduled_to=scheduled_to,
                page=page,
                page_size=page_size,
            ),
            admin_actor_context(principal),
        )
    except ValueError as exc:
        _raise_task_error(exc)
    return BaseResponse(
        data={
            "items": [_admin_record(item) for item in result.items],
            "page": result.page,
            "page_size": result.page_size,
            "total": result.total,
            "total_pages": max(1, (result.total + result.page_size - 1) // result.page_size),
        }
    )


@router.get("/{task_id}", response_model=BaseResponse[dict])
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
        _raise_task_error(exc)
    return BaseResponse(
        data={
            "task": _admin_record(task),
            "attempts": [asdict(item) for item in attempts],
        }
    )


@router.post("/{task_id}/cancel", response_model=BaseResponse[dict])
def cancel_task(
    task_id: int,
    payload: LineTaskActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_task_controller),
):
    task = _control("cancel", task_id, payload, principal)
    _set_task_audit(request, "line.task.cancel", task_id, payload.reason)
    return BaseResponse(data=_task_snapshot(task), message="任務已取消")


@router.post("/{task_id}/run-now", response_model=BaseResponse[dict])
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


@router.post("/{task_id}/retry", response_model=BaseResponse[dict])
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


def _task_snapshot(task: LineDeliveryTaskSnapshot) -> dict[str, object]:
    preview = _message_preview(task.request.payload_json)
    return {
        "id": task.task_id.value,
        "task_id": task.task_id.value,
        "task_type": _legacy_task_type(task.request.source_aggregate_type),
        "to_user_id": task.request.recipient.identity.value,
        "recipient_type": task.request.recipient.recipient_type.value,
        "recipient_identity": task.request.recipient.identity.value,
        "message_kind": task.request.message_kind.value,
        "payload_json": task.request.payload_json,
        "message_content": preview,
        "message_preview": preview,
        "scheduled_at": task.request.scheduled_at,
        "source_aggregate_type": task.request.source_aggregate_type,
        "source_aggregate_identity": task.request.source_aggregate_identity,
        "status": task.status.value,
        "completed_attempts": task.completed_attempts,
    }


def _admin_record(item) -> dict[str, object]:
    preview = _message_preview(item.payload_json)
    return {
        "id": item.task_id.value,
        "task_id": item.task_id.value,
        "task_type": _legacy_task_type(item.source_aggregate_type),
        "to_user_id": item.recipient_identity,
        "recipient_type": item.recipient_type,
        "recipient_identity": item.recipient_identity,
        "message_kind": item.message_kind,
        "message_preview": preview,
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


def _message_preview(payload_json: str) -> str:
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError):
        return ""
    value = payload.get("text") or payload.get("altText") or payload.get("alt_text")
    return str(value)[:160] if value else ""


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

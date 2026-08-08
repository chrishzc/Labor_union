"""Capability-protected read APIs for stored health and alert-target management."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.admin_auth import admin_actor_context, require_line_alert_manager, require_line_monitor_reader
from api.schemas.runtime_health import AlertAdminTargetRequest, AlertTargetEnabledRequest
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository

router = APIRouter(prefix="/api/v1/runtime", tags=["Runtime Health"])


@router.get("/health-status")
def health_status(_=Depends(require_line_monitor_reader)):
    return [_record(item) for item in _query("list_status")]


@router.get("/health-events")
def health_events(limit: int = Query(100, ge=1, le=500), _=Depends(require_line_monitor_reader)):
    return [_event(item) for item in _query("list_events", limit)]


@router.get("/line-alert-targets")
def alert_targets(_=Depends(require_line_monitor_reader)):
    return list(_query("list_targets"))


@router.post("/line-alert-targets/admin")
def add_admin_target(payload: AlertAdminTargetRequest, principal=Depends(require_line_alert_manager)):
    actor = admin_actor_context(principal)
    return {"target_id": _mutate("add_admin_target", payload.admin_user_id, payload.display_name, payload.minimum_status, actor.actor_id)}


@router.patch("/line-alert-targets/{target_id}")
def set_target_enabled(target_id: int, payload: AlertTargetEnabledRequest, _=Depends(require_line_alert_manager)):
    if not _mutate("set_target_enabled", target_id, payload.enabled):
        raise HTTPException(404, "找不到通知目標")
    return {"target_id": target_id, "enabled": payload.enabled}


def _query(method, *args):
    connection = get_connection()
    try:
        return getattr(MySqlRuntimeMonitorRepository(connection), method)(*args)
    finally:
        connection.close()


def _mutate(method, *args):
    connection = get_connection()
    try:
        connection.begin()
        result = getattr(MySqlRuntimeMonitorRepository(connection), method)(*args)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _record(item):
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


def _event(item):
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


__all__ = ["router"]

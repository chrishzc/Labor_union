"""
================================================================================
檔案名稱: api/routes/line_admin.py
功能說明: LINE 管理中心總覽 API，提供系統健康狀態、Worker 狀態與管理功能清單
================================================================================
"""

from __future__ import annotations

import os
from pathlib import Path

import pymysql
from fastapi import APIRouter, Depends

from api.dependencies.admin_auth import require_line_viewer
from api.schemas.base import BaseResponse
from line.worker import worker_is_running
from infrastructure.mysql.mysql_adapter import get_connection


router = APIRouter(
    prefix="/api/v1/line/admin",
    tags=["LINE Admin"],
    dependencies=[Depends(require_line_viewer)],
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _configured(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value and not value.startswith("your_") and value != "mock_token")


def _database_health() -> dict:
    try:
        conn = get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT 1 AS ok")
                database_ok = bool(cursor.fetchone()["ok"])
                cursor.execute(
                    """
                    SELECT status, COUNT(*) AS total
                    FROM line_tasks
                    GROUP BY status
                    """
                )
                task_counts = {row["status"]: int(row["total"]) for row in cursor.fetchall()}
        finally:
            conn.close()
        return {"ok": database_ok, "line_task_counts": task_counts}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/health", response_model=BaseResponse[dict])
def line_admin_health():
    database = _database_health()
    status_text = "healthy" if database.get("ok") and worker_is_running() else "degraded"
    return BaseResponse(
        data={
            "status": status_text,
            "database": database,
            "worker": {"running": worker_is_running()},
            "line_credentials": {
                "channel_secret": _configured("LINE_CHANNEL_SECRET"),
                "channel_access_token": _configured("LINE_CHANNEL_ACCESS_TOKEN"),
                "liff_id": _configured("LINE_LIFF_ID"),
            },
        }
    )


@router.get("/capabilities", response_model=BaseResponse[dict])
def line_admin_capabilities():
    return BaseResponse(
        data={
            "stage": "5.6",
            "available": {
                "health_overview": True,
                "message_template_api": True,
                "message_schedule_api": True,
                "message_schedule_editor": True,
                "line_task_admin_api": True,
                "line_task_attempt_history": True,
                "rich_menu_api": True,
                "rich_menu_editor": True,
                "rich_menu_publication_history": True,
                "liff_config_api": True,
                "liff_config_editor": True,
                "liff_runtime_config": True,
                "liff_revision_history": True,
                "customer_service_config_api": True,
                "staff_review_api": True,
                "staff_review_management": True,
                "admin_session": True,
                "role_permissions": True,
                "audit_log": True,
            },
            "planned_pages": [
                "LINE 設定中心",
                "客服入口",
                "操作紀錄",
            ],
            "config_files": {
                "message_templates": (PROJECT_ROOT / "config/message_templates.json").exists(),
                "message_schedules": (PROJECT_ROOT / "config/message_schedules.json").exists(),
                "line_menus": (PROJECT_ROOT / "config/line_menu.json").exists(),
                "liff": (PROJECT_ROOT / "config/liff_settings.json").exists(),
                "customer_service": (PROJECT_ROOT / "config/customer_service.json").exists(),
            },
        }
    )

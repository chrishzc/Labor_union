# -*- coding: utf-8 -*-
"""
================================================================================
檔案名稱: line/line_bot.py
功能說明: LINE Bot 子路由，負責 Webhook、LIFF、使用者事件、身分切換與 LINE 訊息任務建立
================================================================================
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import pymysql
import os
import asyncio
import sys
import requests
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from fastapi.responses import FileResponse
from line.worker import wake_worker
from api.dependencies.line_runtime import line_webhook_runtime_mode
from api.line_webhook_boundary import canonical_line_webhook
from subsystems.line.runtime_contracts import LineRuntimeMode
# Task 97 still audits this fail-closed compatibility module by path.  Import it
# here so the retained surface is explicit until that governance consumer moves.
from subsystems.line import user_lifecycle as _retired_user_lifecycle  # noqa: F401
from subsystems.line.client_binding_application import bind_client
from subsystems.line.liff_identity_verification import (
    LiffIdentityError,
    liff_token_required,
    resolve_line_user_id,
)
from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationIntent,
)
from subsystems.case_import.provisional_registration_application import (
    ProvisionalRegistrationConflictError,
)
from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
from api.dependencies.provisional_registration import build_provisional_registration_application

# 載入環境變數
load_dotenv()

# 確保 sys.path 能載入 services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from infrastructure.mysql.mysql_adapter import get_connection as get_db_connection

def get_setting(key: str, default: str = "") -> str:
    """從環境變數讀取設定，取代舊版 admin.settings_manager"""
    env_key = key.upper()
    return os.getenv(env_key, default)

def _notify_development_reviewer(request_type: str, request_id: str | int) -> None:
    """Push one review event to the local dev supervisor; never affect webhook success."""
    notify_url = os.getenv("DEV_REVIEW_NOTIFY_URL", "").strip()
    if not notify_url:
        return
    try:
        response = requests.post(
            notify_url,
            json={"type": request_type, "request_id": str(request_id)},
            timeout=1,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[LINE Review] Development notification failed: {exc}")


def _liff_url(query: str = "") -> str:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        liff_id = get_setting("line_liff_id", "").strip()
    if not liff_id:
        return "LIFF 尚未完成設定，請聯絡工會人員。"
    return f"https://liff.line.me/{liff_id}/{query}"


router = APIRouter(tags=["LINE"])


def _require_legacy_line_surface(replacement: str) -> None:
    if line_webhook_runtime_mode() is not LineRuntimeMode.CANONICAL:
        return
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_line_route_retired",
            "message": "此 LINE 舊入口已在 Canonical Runtime 退出。",
            "replacement": replacement,
        },
    )


# LINE LIFF 配置獲取端點
@router.get("/api/line/config")
async def get_line_config():
    _require_legacy_line_surface("/api/v1/line/identity/runtime-config")
    liff_id = os.getenv("LINE_LIFF_ID", "")
    if not liff_id or liff_id == "your_liff_id_here":
        liff_id = get_setting("line_liff_id", "")
    return {
        "liff_id": liff_id,
        "identity_verification_required": liff_token_required(),
        "line_login_channel_id_configured": bool(
            os.getenv("LINE_LOGIN_CHANNEL_ID", "").strip()
        ),
    }


async def _trusted_line_user_id(id_token: str | None, fallback_user_id: str | None) -> str:
    try:
        return await asyncio.to_thread(
            resolve_line_user_id,
            id_token=id_token,
            development_user_id=fallback_user_id,
        )
    except LiffIdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

async def _find_client_info(trusted_user_id: str):
    """查詢使用者的 LINE ID 是否已有綁定紀錄，有的話回傳最近一筆姓名電話以利自動帶入"""
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT name, phone FROM clients WHERE line_user_id = %s ORDER BY id DESC LIMIT 1", (trusted_user_id,))
            client = cursor.fetchone()
            if client:
                return {"status": "success", "client": client}
            return {"status": "not_found"}
    except Exception as e:
        print(f"[API Client Info] Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

# 帳號綁定請求 Model
class LineBindPayload(BaseModel):
    name: str
    phone: str
    line_user_id: str = ""
    line_id_token: str = ""
    force_rebind: bool = False

@router.post("/api/line/bind")
async def line_bind(payload: LineBindPayload):
    name = payload.name.strip()
    phone = payload.phone.strip()
    norm_phone = "".join(filter(str.isdigit, phone))
    line_user_id = ""
    if payload.line_id_token:
        try:
            line_user_id = await _trusted_line_user_id(payload.line_id_token, payload.line_user_id)
        except Exception:
            line_user_id = payload.line_user_id or "preview-user"
    else:
        line_user_id = payload.line_user_id or "preview-user"

    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, name, phone, case_no, line_user_id FROM clients "
                "WHERE name = %s AND REPLACE(REPLACE(phone, '-', ''), ' ', '') = %s "
                "ORDER BY id DESC LIMIT 1",
                (name, norm_phone),
            )
            client = cursor.fetchone()

            # 狀態 C：查無案號 / 名冊未同步
            if not client:
                return {
                    "status": "state_c",
                    "kind": "not_found",
                    "name": name,
                    "phone": phone,
                    "message": "市府名冊同步中，即將為您載入工會需求調查表單...",
                }

            existing_line_user = client.get("line_user_id")
            if existing_line_user and line_user_id and existing_line_user != line_user_id and not payload.force_rebind:
                return {
                    "status": "confirm_rebind",
                    "message": "本筆訂單已有綁定另一個帳戶，請問是否重新綁定？",
                }

            case_no = client.get("case_no") or ""
            cursor.execute(
                "SELECT id FROM beclass_records WHERE client_id = %s OR (case_no = %s AND %s <> '') LIMIT 1",
                (client["id"], case_no, case_no),
            )
            has_survey = cursor.fetchone() is not None

            if line_user_id and not line_user_id.startswith("local-") and not line_user_id.startswith("mock-") and not line_user_id.startswith("client-"):
                cursor.execute(
                    "UPDATE clients SET line_user_id = %s WHERE id = %s",
                    (line_user_id, client["id"]),
                )
                conn.commit()

            # 狀態 A：舊客完全命中，無需重複填問卷
            if case_no and has_survey:
                wake_worker()
                return {
                    "status": "state_a",
                    "client_name": client["name"],
                    "case_no": case_no,
                    "message": "舊客完全命中！綁定成功，無需重複填寫問卷。",
                }

            # 狀態 B：有案號但缺問卷
            return {
                "status": "state_b",
                "client_name": client["name"],
                "name": client["name"],
                "phone": client["phone"] or phone,
                "case_no": case_no,
                "message": "已找到您的案件，正在為您載入需求調查表單...",
            }
    except Exception as error:
        print(f"[API Bind] State machine fallback: {error}")
        return {
            "status": "state_c",
            "name": name,
            "phone": phone,
            "message": "市府名冊同步中，即將為您載入工會需求調查表單...",
        }
    finally:
        conn.close()

@router.get("/api/line/rebind_requests")
def get_rebind_requests() -> None:
    _raise_legacy_review_api_gone()


def _raise_legacy_review_api_gone() -> None:
    """Prevent legacy internal callers from bypassing typed review authorization."""
    raise HTTPException(
        status_code=410,
        detail={
            "code": "line_review_api_retired",
            "replacement": "/api/v1/line/identity/reviews",
        },
    )


class LineIdentityPayload(BaseModel):
    line_user_id: str = ""
    line_id_token: str = ""


@router.post("/api/line/client-info")
async def post_client_info(payload: LineIdentityPayload):
    _require_legacy_line_surface("/api/v1/line/identity/customer/preview")
    trusted_user_id = await _trusted_line_user_id(
        payload.line_id_token,
        payload.line_user_id,
    )
    return await _find_client_info(trusted_user_id)


@router.get("/api/line/client-info")
async def get_client_info(userId: str = ""):
    """Development-compatible legacy endpoint; production requires POST with an ID token."""
    _require_legacy_line_surface("/api/v1/line/identity/customer/preview")
    trusted_user_id = await _trusted_line_user_id(None, userId)
    return await _find_client_info(trusted_user_id)

@router.post("/api/line/rebind_requests/approve")
def approve_rebind_request() -> None:
    _raise_legacy_review_api_gone()

@router.post("/api/line/rebind_requests/reject")
def reject_rebind_request() -> None:
    _raise_legacy_review_api_gone()

from typing import Optional, Dict, Any

class LineRegisterPayload(BaseModel):
    name: str
    phone: str
    expected_date: str
    service_days: int
    address: str
    line_user_id: str = ""
    line_id_token: str = ""
    liff_config_revision: Optional[str] = ""
    id_number: Optional[str] = ""
    birth_date: Optional[str] = ""
    gender: Optional[str] = ""
    email: Optional[str] = ""
    tel: Optional[str] = ""
    ext: Optional[str] = ""
    city: Optional[str] = ""
    zip_code: Optional[str] = ""
    survey_details: Dict[str, Any] = {}


@router.post("/api/line/register")
async def line_register(payload: LineRegisterPayload):
    _require_legacy_line_surface("/api/v1/line/identity/customer/apply")
    line_user_id = await _trusted_line_user_id(
        payload.line_id_token,
        payload.line_user_id,
    )
    conn = get_db_connection()
    try:
        receipt = build_provisional_registration_application(conn).apply(
            _provisional_registration_intent(payload, line_user_id)
        )
        if receipt.worker_wakeup_required:
            wake_worker()
        return {
            "status": "success",
            "client_id": receipt.client_id,
            "client_name": receipt.client_name,
            "case_no": None,
            "replayed": receipt.replayed,
        }
    except ProvisionalRegistrationConflictError:
        return {"status": "error", "message": "已有不同內容的待核發登記，請聯絡工會行政人員核對。"}
    except (ProvisionalRegistrationDomainError, ProvisionalRegistrationStorageError) as error:
        print(f"[API Register] Error: {error}")
        return {"status": "error", "message": f"建檔失敗: {error}"}
    finally:
        conn.close()


def _provisional_registration_intent(payload, line_user_id):
    return ProvisionalRegistrationIntent(
        line_user_id=line_user_id,
        name=payload.name,
        phone=payload.phone,
        expected_date=payload.expected_date,
        service_days=payload.service_days,
        address=payload.address,
        gender=payload.gender,
        email=payload.email,
        birth_date=payload.birth_date,
        tel=payload.tel,
        ext=payload.ext,
        city=payload.city,
        zip_code=payload.zip_code,
        id_number=payload.id_number,
        liff_config_revision=payload.liff_config_revision,
        survey_details=payload.survey_details,
    )

@router.get("/")
async def health_check():
    db_ok = False
    db_msg = ""
    try:
        conn = get_db_connection()
        conn.close()
        db_ok = True
        db_msg = "Database connected"
    except Exception as e:
        db_ok = False
        db_msg = str(e)
        
    return {
        "status": "healthy",
        "api_version": "1.0.0",
        "database": {
            "connected": db_ok,
            "message": db_msg
        }
    }

@router.post("/")
async def root_post(payload: dict, request: Request):
    if "events" in payload:
        raise HTTPException(status_code=400, detail="Use /webhook/line so the raw signed body can be verified")
    return {"status": "active", "message": "Root POST active"}

@router.get("/liff-page")
@router.get("/gateway")
async def serve_gateway_page():
    """Compatibility entry for older LIFF endpoint URLs."""
    return FileResponse("line/static/identity.html")

@router.get("/bind-page")
async def serve_bind_page():
    """提供舊客查詢與綁定專用的路徑"""
    _require_legacy_line_surface("/line-identity")
    return FileResponse("line/static/bind.html")

@router.get("/register-page")
async def serve_register_page():
    """全新客戶原生註冊頁面"""
    _require_legacy_line_surface("/line-identity")
    return FileResponse("line/static/register.html")


@router.get("/api/line/staff/review-requests")
def list_staff_review_requests() -> None:
    _raise_legacy_review_api_gone()


@router.post("/api/line/staff/review-requests/{request_type}/{request_id}/approve")
def approve_staff_review_request(
    request_type: str,
    request_id: str,
) -> None:
    _raise_legacy_review_api_gone()


@router.post("/api/line/staff/review-requests/{request_type}/{request_id}/reject")
def reject_staff_review_request(
    request_type: str,
    request_id: str,
) -> None:
    _raise_legacy_review_api_gone()


@router.put("/api/line/users/{user_id}/role/{role}")
def set_line_user_role(user_id: str, role: str) -> None:
    """Retired writer; canonical identity administration owns role binding."""
    raise HTTPException(
        status_code=410,
        detail={
            "code": "line_role_api_retired",
            "replacement": "/api/v1/line/identity",
        },
    )

# ----------------- 1. LINE WEBHOOK 接收 -----------------
@router.get("/webhook/line")
@router.get("/webhook/line/")
@router.get("/webhook")
@router.get("/webhook/")
async def line_webhook_get():
    print("[LINE Webhook] Received GET request (possibly URL verification or redirect)")
    return {"status": "ok", "message": "LINE Webhook endpoint is active"}

@router.post("/webhook/line")
@router.post("/webhook/line/")
@router.post("/webhook")
@router.post("/webhook/")
async def line_webhook(request: Request):
    """The public webhook has one canonical inbox boundary after WP35 cutover."""
    return await canonical_line_webhook(request)

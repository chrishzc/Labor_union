# -*- coding: utf-8 -*-
"""
================================================================================
檔案名稱: line/line_bot.py
功能說明: LINE Bot 子路由，負責 Webhook、LIFF、使用者事件、身分切換與 LINE 訊息任務建立
================================================================================
"""
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
import pymysql
import os
import json
import asyncio
import sys
import secrets
import requests
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from fastapi.responses import FileResponse
from line.worker import wake_worker
from api.dependencies.line_runtime import line_webhook_runtime_mode
from api.routes.line_webhook import canonical_line_webhook
from subsystems.line.runtime_contracts import LineRuntimeMode
from line.security import verify_line_signature
from subsystems.line.delivery_task_workflow import enqueue_line_task
from subsystems.line.postback_intent_registry import (
    LinePostbackIntentError,
    handle_matching_willingness,
)
from subsystems.line.identity_review_workflow import submit_staff_verification_in_transaction
from subsystems.line.client_binding_application import bind_client
from subsystems.line.rich_menu_publication_workflow import get_current_rich_menu_id
from subsystems.line.webhook_inbox import mark_events_completed, register_event
from subsystems.line.liff_identity_verification import (
    LiffIdentityError,
    liff_token_required,
    resolve_line_user_id,
)
from domains.case_import.provisional_registration import ProvisionalRegistrationIntent
from subsystems.case_import.provisional_registration_application import (
    ProvisionalRegistrationConflictError,
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationStorageError,
    build_provisional_registration_application,
)
from subsystems.line.user_lifecycle import (
    activate_follow,
    apply_role,
    block_unfollow,
    cancel_pending_onboarding,
)

# 載入環境變數
load_dotenv()

# 確保 sys.path 能載入 services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from infrastructure.mysql.mysql_adapter import get_connection as get_db_connection

def get_setting(key: str, default: str = "") -> str:
    """從環境變數讀取設定，取代舊版 admin.settings_manager"""
    env_key = key.upper()
    return os.getenv(env_key, default)

def load_message_templates():
    """Return enabled text templates keyed by template id."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "message_templates.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            item["id"]: item["content"]
            for item in data.get("templates", [])
            if item.get("enabled", True) and item.get("message_type", "text") == "text"
        }
    except Exception as e:
        print(f"[LINE Webhook] Failed to load message templates: {e}")
        return {}


def _load_rich_menu_id(role: str) -> str:
    current_id = get_current_rich_menu_id(role)
    if current_id:
        return current_id
    key_by_role = {
        "staff": "staff_rich_menu_id",
        "union_staff": "union_staff_rich_menu_id",
        "customer": "default_rich_menu_id",
    }
    path = os.path.join(os.path.dirname(__file__), "..", "config", "rich_menu_ids.json")
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream).get(key_by_role[role], "")
    except (OSError, ValueError, KeyError):
        return ""


def _require_internal_api_key(x_internal_api_key: str | None) -> None:
    expected = os.getenv("INTERNAL_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Internal API authentication is not configured")
    if not secrets.compare_digest(x_internal_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _notify_development_reviewer(request_type: str, request_id: str | int) -> None:
    """Push one review event to the local dev supervisor; never affect webhook success."""
    notify_url = os.getenv("DEV_REVIEW_NOTIFY_URL", "").strip()
    internal_key = os.getenv("INTERNAL_API_KEY", "").strip()
    if not notify_url or not internal_key:
        return
    try:
        response = requests.post(
            notify_url,
            json={"type": request_type, "request_id": str(request_id)},
            headers={"X-Internal-API-Key": internal_key},
            timeout=1,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[LINE Review] Development notification failed: {exc}")


def _create_onboarding_tasks(cursor, user_id: str, source_event_id: str | None) -> None:
    schedule_path = os.path.join(os.path.dirname(__file__), "..", "config", "message_schedules.json")
    templates = load_message_templates()
    try:
        with open(schedule_path, "r", encoding="utf-8") as stream:
            schedule_config = json.load(stream)
            schedules = schedule_config.get("schedules", [])
    except (OSError, ValueError):
        return
    onboarding = next((item for item in schedules if item.get("id") == "new_user_onboarding" and item.get("enabled")), None)
    if not onboarding:
        return
    restart_on_refollow = bool(onboarding.get("restart_on_refollow", False))
    if restart_on_refollow:
        cancel_pending_onboarding(cursor, user_id)
    for step in onboarding.get("steps", []):
        template_id = step.get("template_id")
        content = templates.get(template_id)
        if not content:
            continue
        send_time = step.get("send_time", "10:00")
        day = int(step.get("day", 0))
        hour, minute = map(int, send_time.split(":"))
        schedule_zone = ZoneInfo(schedule_config.get("timezone", "Asia/Taipei"))
        local_now = datetime.now(schedule_zone)
        local_target = (local_now + timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        # MySQL currently stores UTC in a timezone-naive DATETIME column.
        scheduled_at = local_target.astimezone(timezone.utc).replace(tzinfo=None)
        if restart_on_refollow and source_event_id:
            idempotency_key = f"onboarding:{user_id}:{source_event_id}:d{day}"
        else:
            idempotency_key = f"onboarding:{user_id}:d{day}"
        enqueue_line_task(
            cursor, to_user_id=user_id, message_content=content,
            scheduled_at=scheduled_at, source_event_id=source_event_id,
            idempotency_key=idempotency_key,
        )


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
    _require_legacy_line_surface("/api/v1/line/identity/customer/apply")
    name = payload.name.strip()
    phone = payload.phone.strip()
    line_user_id = await _trusted_line_user_id(
        payload.line_id_token,
        payload.line_user_id,
    )
    conn = get_db_connection()
    try:
        outcome = bind_client(
            conn, name=name, phone=phone, line_user_id=line_user_id,
            force_rebind=payload.force_rebind,
        )
        return _line_binding_response(outcome)
    except Exception as error:
        print(f"[API Bind] Binding process failed: {error}")
        return {
            "status": "error",
            "message": f"伺服器錯誤：{error}"
        }
    finally:
        conn.close()


def _line_binding_response(outcome: dict) -> dict:
    kind = outcome["kind"]
    if kind == "not_found":
        return {"status": "error", "message": "查無此姓名與電話之登記資料，請確認輸入是否正確，或聯絡公會專員。\n如尚未登記政府補助請先至政府官網登記"}
    if kind == "confirm_rebind":
        return {"status": "confirm_rebind", "message": "本筆訂單已有綁定另一個帳戶，請問是否重新綁定？"}
    if kind == "pending_approval":
        _notify_development_reviewer("client_rebind", outcome["request_id"])
        return {"status": "pending_approval", "message": "您的帳號重新綁定申請已送出，請耐心等待服務人員審核與確認。"}
    client = outcome["client"]
    wake_worker()
    return {"status": "success", "message": "綁定與查詢成功！", "client_name": client["name"], "client_id": client["id"], "case_no": client["case_no"]}

@router.get("/api/line/rebind_requests")
def get_rebind_requests() -> None:
    _raise_legacy_review_api_gone()


def _raise_legacy_review_api_gone() -> None:
    """Prevent legacy internal callers from bypassing typed review authorization."""
    raise HTTPException(
        status_code=410,
        detail={
            "code": "line_review_api_retired",
            "replacement": "/api/v1/line/review-requests",
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
    """前導選擇頁面 (自動相容舊版 LIFF 設定)"""
    _require_legacy_line_surface("/line-identity")
    return FileResponse("line/static/gateway.html")

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
def set_line_user_role(user_id: str, role: str, x_internal_api_key: str | None = Header(default=None)):
    """Internal role administration endpoint for customer/staff/union_staff."""
    _require_legacy_line_surface("/api/v1/line/identity")
    _require_internal_api_key(x_internal_api_key)
    if role not in {"customer", "staff", "union_staff"}:
        raise HTTPException(status_code=422, detail="Unsupported LINE user role")
    conn = get_db_connection()
    try:
        apply_role(conn, user_id, role)
        return {"status": "success", "line_user_id": user_id, "role": role}
    finally:
        conn.close()

# ----------------- 1. LINE WEBHOOK 接收 -----------------
class LineWebhookPayload(BaseModel):
    events: list = []
    destination: str = ""

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
    if line_webhook_runtime_mode() is LineRuntimeMode.CANONICAL:
        return await canonical_line_webhook(request)
    raw_body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if not verify_line_signature(raw_body, signature, channel_secret):
        raise HTTPException(status_code=401, detail="Invalid LINE webhook signature")
    try:
        payload = LineWebhookPayload.model_validate_json(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid LINE webhook payload") from exc
    print(f"[LINE Webhook] Received line webhook. Events count: {len(payload.events)}")
    
    review_notifications: list[tuple[str, int]] = []
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            for event in payload.events:
                if not register_event(cursor, event):
                    print(f"[LINE Webhook] Duplicate event ignored: {event.get('webhookEventId')}")
                    continue
                event_type = event.get("type")
                
                # 處理新用戶加入好友 (follow) 事件
                if event_type == "follow":
                    source = event.get("source", {})
                    user_id = source.get("userId", "")
                    print(f"[LINE Webhook] Follow event received from User: {user_id}")
                    
                    if user_id:
                        activate_follow(cursor, user_id)
                        liff_id = os.getenv("LINE_LIFF_ID", "")
                        if not liff_id or liff_id == "your_liff_id_here":
                            liff_id = get_setting("line_liff_id", "")
                            
                        # 決定 LIFF 網頁的綁定連結 (若無真實 LIFF ID 則回退至測試 URL)
                        if liff_id and liff_id != "your_liff_id_here" and liff_id.strip() != "":
                            bind_url = f"https://liff.line.me/{liff_id}"
                        else:
                            base_url = os.getenv("BASE_URL", "").strip().rstrip("/")
                            if base_url:
                                bind_url = f"{base_url}/gateway?userId={user_id}"
                            else:
                                host = request.headers.get("host", "127.0.0.1:8000")
                                proto = request.headers.get("x-forwarded-proto", "http")
                                bind_url = f"{proto}://{host}/gateway?userId={user_id}"
                            
                        welcome_msg = (
                            "您好！感謝您加入新竹市月子公會官方帳號。\n"
                            "為了提供您更完整的服務，請點擊以下連結進行帳號與訂單綁定：\n\n"
                            f"{bind_url}\n\n"
                            "請於網頁中填寫您在政府補助登記時的姓名與電話，以利系統進行安全配對。如有任何疑問，歡迎隨時聯絡公會專員。"
                        )
                        
                        # 寫入推播任務佇列，由背景發送
                        enqueue_line_task(
                            cursor, to_user_id=user_id, message_content=welcome_msg,
                            source_event_id=event.get("webhookEventId"),
                            idempotency_key=f"welcome:{event.get('webhookEventId') or user_id}",
                        )
                        _create_onboarding_tasks(cursor, user_id, event.get("webhookEventId"))
                        print(f"[LINE Webhook] Queued welcome message for new user {user_id}")

                elif event_type == "unfollow":
                    source = event.get("source", {})
                    user_id = source.get("userId", "")
                    if user_id:
                        block_unfollow(cursor, user_id)
                
                elif event_type == "postback":
                    postback_data = event["postback"].get("data", "")
                    user_id = event.get("source", {}).get("userId", "")
                    print(f"[LINE Webhook] Postback data received: {postback_data}")
                    
                    params = {}
                    for item in postback_data.split("&"):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            params[k] = v
                            
                    action = params.get("action")
                    case_no = params.get("case_no")
                    staff_id = params.get("staff_id")
                    
                    if not action or not case_no:
                        continue

                    if action in {"willing", "unwilling"} and (
                        "plan_id" in params or "segment_id" in params
                    ):
                        try:
                            result = handle_matching_willingness(
                                params, event.get("webhookEventId", ""), user_id
                            )
                        except LinePostbackIntentError as exc:
                            print(f"[LINE Webhook] Invalid matching postback: {exc}")
                            continue
                        print(f"[LINE Webhook] Matching willingness recorded: {result}")
                        continue
                        
                    legacy_actions = {"willing", "unwilling", "client_approve", "client_reject"}
                    if action in legacy_actions:
                        enqueue_line_task(
                            cursor,
                            to_user_id=user_id,
                            message_content="此媒合訊息已過期，請由工會提供的最新媒合流程重新操作。",
                            source_event_id=event.get("webhookEventId"),
                            idempotency_key=f"retired-legacy-postback:{event.get('webhookEventId') or case_no}",
                        )
                        print(f"[LINE Webhook] Retired legacy postback ignored: {action}")
                        continue
                # 處理文字對答與 RAG
                elif event_type == "message":
                    message = event.get("message", {})
                    if message.get("type") == "text":
                        user_text = message.get("text", "")
                        source = event.get("source", {})
                        user_id = source.get("userId", "")
                        reply_token = event.get("replyToken", "")
                        print(f"[LINE Webhook] Text message received from {user_id}: {user_text}")

                        cursor.execute("SELECT role FROM line_users WHERE line_user_id=%s", (user_id,))
                        role_row = cursor.fetchone()
                        current_role = role_row["role"] if role_row else "customer"
                        if current_role == "union_staff" and user_text.strip() in {"工會選單", "開啟客服系統", "月嫂驗證管理"}:
                            enqueue_line_task(
                                cursor, to_user_id=user_id, task_type="rich_menu_link",
                                payload={
                                    "rich_menu_id": _load_rich_menu_id("union_staff"),
                                    "success_message": "已切換至工會人員客服選單。",
                                },
                                source_event_id=event.get("webhookEventId"),
                                idempotency_key=f"union-menu:{event.get('webhookEventId')}",
                            )
                            continue

                        # 攔截「我是月嫂」並建立人工確認請求，不直接切換身分。
                        if "我是月嫂" in user_text:
                            result = submit_staff_verification_in_transaction(
                                cursor,
                                user_id,
                                source_event_id=event.get("webhookEventId"),
                            )
                            request_id = result["request_id"]
                            review_notifications.append(("staff_verification", request_id))
                            print(f"[LINE Webhook] Staff verification request #{request_id} created for {user_id}")
                            continue
                            
                        # 攔截「esc」關鍵字恢復預設選單
                        if user_text.lower().strip() == "esc":
                            replies = load_message_templates()
                            enqueue_line_task(
                                cursor, to_user_id=user_id, task_type="rich_menu_unlink",
                                payload={"success_message": replies.get("esc_success", "已切換回一般用戶選單。")},
                                source_event_id=event.get("webhookEventId"),
                                idempotency_key=f"menu-unlink:{event.get('webhookEventId')}",
                            )
                            continue

                        # 攔截「查詢訂單」或「綁定」關鍵字對話流
                        if "查詢訂單" in user_text or "綁定" in user_text:
                            liff_id = os.getenv("LINE_LIFF_ID", "")
                            if not liff_id or liff_id == "your_liff_id_here":
                                liff_id = get_setting("line_liff_id", "")
                                
                            if liff_id and liff_id != "your_liff_id_here" and liff_id.strip() != "":
                                bind_url = f"https://liff.line.me/{liff_id}"
                            else:
                                base_url = os.getenv("BASE_URL", "").strip().rstrip("/")
                                if base_url:
                                    bind_url = f"{base_url}/gateway?userId={user_id}"
                                else:
                                    host = request.headers.get("host", "127.0.0.1:8000")
                                    proto = request.headers.get("x-forwarded-proto", "http")
                                    bind_url = f"{proto}://{host}/gateway?userId={user_id}"
                                
                            replies = load_message_templates()
                            reply_msg = replies.get("bind_link_msg").replace("{bind_url}", bind_url)
                            
                            enqueue_line_task(
                                cursor, to_user_id=user_id, message_content=reply_msg,
                                source_event_id=event.get("webhookEventId"),
                                idempotency_key=f"bind-link:{event.get('webhookEventId')}",
                            )
                            print(f"[LINE Webhook] Intercepted keyword '{user_text}', queued query link for User: {user_id}")
                            continue
                        
                        # Legacy runtime cannot provide reviewed sources/citations safely.
                        enqueue_line_task(
                            cursor,
                            to_user_id=user_id,
                            message_content="此問題將由工會人員協助確認，請稍候。",
                            source_event_id=event.get("webhookEventId"),
                            idempotency_key=f"knowledge-manual-fallback:{event.get('webhookEventId')}",
                        )

                        
            completed_event_ids = [
                event.get("webhookEventId") for event in payload.events
                if event.get("webhookEventId")
            ]
            mark_events_completed(cursor, completed_event_ids)
            conn.commit()
            wake_worker()
            for request_type, request_id in review_notifications:
                _notify_development_reviewer(request_type, request_id)
    except Exception as e:
        conn.rollback()
        print(f"[LINE Webhook] Webhook handler failed: {e}")
        raise HTTPException(status_code=500, detail="LINE webhook processing failed") from e
    finally:
        conn.close()
        
    return {"status": "ok"}

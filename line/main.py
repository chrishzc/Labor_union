# -*- coding: utf-8 -*-
"""
File: api/main.py
Description: LINE 與 好好簽 Webhook 接收後端服務 (API Server)
"""
from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel
import pymysql
import os
import json
import asyncio
import requests
import sys
from datetime import datetime, timedelta, date
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 載入環境變數
load_dotenv()

# 確保 sys.path 能載入 services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.db_service import get_connection as get_db_connection, calculate_attendance_schedule

def get_setting(key: str, default: str = "") -> str:
    """從環境變數讀取設定，取代舊版 admin.settings_manager"""
    env_key = key.upper()
    return os.getenv(env_key, default)

def load_webhook_replies():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "webhook_replies.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[LINE Webhook] Failed to load webhook replies: {e}")
        return {}


# ----------------- 背景非同步 LINE 發送器 Daemon -----------------
async def line_message_sender_daemon():
    print("[LINE Daemon] Background LINE sender daemon started")
    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
    
    while True:
        try:
            await asyncio.sleep(2.0) # 每 2 秒輪詢一次
            
            conn = get_db_connection()
            pending_tasks = []
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT * FROM line_push_tasks 
                        WHERE status = 'pending' 
                        ORDER BY id ASC LIMIT 5
                    """)
                    pending_tasks = cursor.fetchall()
            finally:
                conn.close()
                
            for task in pending_tasks:
                task_id = task["id"]
                to_user = task["to_user_id"]
                content = task["message_content"]
                
                print(f"[LINE Sender] Found pending task #{task_id} for User: {to_user}")
                
                success = False
                err_msg = ""
                
                # Mock 發送 (避免 print 訊息內容以防 CP950 崩潰)
                if line_token == "mock_token" or not line_token:
                    print(f"[LINE Mock] Sent message successfully for Task ID: {task_id}")
                    success = True
                else:
                    # 調用 LINE Messaging API
                    url = "https://api.line.me/v2/bot/message/push"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {line_token}"
                    }
                    payload = {
                        "to": to_user,
                        "messages": [
                            {
                                "type": "text",
                                "text": content
                            }
                        ]
                    }
                    try:
                        res = requests.post(url, json=payload, headers=headers, timeout=5)
                        if res.status_code == 200:
                            success = True
                        else:
                            success = False
                            err_msg = f"HTTP {res.status_code}: {res.text}"
                    except Exception as ex:
                        success = False
                        err_msg = str(ex)
                        
                # 更新狀態
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        if success:
                            cursor.execute("UPDATE line_push_tasks SET status = 'sent' WHERE id = %s", (task_id,))
                        else:
                            cursor.execute("UPDATE line_push_tasks SET status = 'failed' WHERE id = %s", (task_id,))
                            print(f"[LINE Sender] Task #{task_id} failed: {err_msg}")
                        conn.commit()
                finally:
                    conn.close()
                    
        except Exception as e:
            print(f"[LINE Daemon] Daemon loop error: {e}")

# 生命週期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動背景線程
    daemon_task = asyncio.create_task(line_message_sender_daemon())
    yield
    # 關閉背景線程
    daemon_task.cancel()
    try:
        await daemon_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Labor Union Webhook & API",
    description="LINE & BreezySign Webhook receiver backend",
    version="1.0.0",
    lifespan=lifespan
)

# 掛載靜態目錄以託管 LIFF 網頁
app.mount("/static", StaticFiles(directory="line/static"), name="static")

# LINE LIFF 配置獲取端點
@app.get("/api/line/config")
async def get_line_config():
    liff_id = os.getenv("LINE_LIFF_ID", "")
    if not liff_id or liff_id == "your_liff_id_here":
        liff_id = get_setting("line_liff_id", "")
    return {"liff_id": liff_id}

@app.get("/api/line/client-info")
async def get_client_info(userId: str):
    """查詢使用者的 LINE ID 是否已有綁定紀錄，有的話回傳最近一筆姓名電話以利自動帶入"""
    if not userId:
        return {"status": "not_found"}
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT name, phone FROM clients WHERE line_user_id = %s ORDER BY id DESC LIMIT 1", (userId,))
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
    line_user_id: str
    force_rebind: bool = False

@app.post("/api/line/bind")
async def line_bind(payload: LineBindPayload):
    name = payload.name.strip()
    phone = payload.phone.strip()
    line_user_id = payload.line_user_id.strip()
    
    print(f"[API Bind] Attempting to bind name={name}, phone={phone} to line_user_id={line_user_id}")
    
    # 正規化電話：去除所有空白與 "-" 
    normalized_phone = phone.replace(" ", "").replace("-", "")
    
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. 進行姓名與電話之雙重精確比對（防同名同姓錯誤綁定），同時查詢現有的 line_user_id
            cursor.execute("""
                SELECT id, name, line_user_id FROM clients 
                WHERE name = %s AND REPLACE(REPLACE(phone, '-', ''), ' ', '') = %s 
                ORDER BY id DESC LIMIT 1
            """, (name, normalized_phone))
            
            client = cursor.fetchone()
            
            if not client:
                return {
                    "status": "error",
                    "message": "查無此姓名與電話之登記資料，請確認輸入是否正確，或聯絡公會專員。\n如尚未登記政府補助請先至政府官網登記"
                }
                
            client_id = client["id"]
            db_name = client["name"]
            db_line_user_id = client["line_user_id"]
            
            # 2. 處理 line_user_id 寫入與覆蓋邏輯
            if db_line_user_id and db_line_user_id.strip() != "" and db_line_user_id != line_user_id:
                if not payload.force_rebind:
                    # 發現有不同帳號，且未強制覆蓋，暫停並回傳確認重綁狀態
                    return {
                        "status": "confirm_rebind",
                        "message": "本筆訂單已有綁定另一個帳戶，請問是否重新綁定？"
                    }
                else:
                    # 使用者同意強制重新綁定
                    cursor.execute("""
                        UPDATE clients 
                        SET line_user_id = %s 
                        WHERE id = %s
                    """, (line_user_id, client_id))
                    print(f"[API Bind] Forced rebind success: client_id={client_id} rebound to line_user_id={line_user_id}")
            elif not db_line_user_id or db_line_user_id.strip() == "":
                # 原本為空，正常綁定
                cursor.execute("""
                    UPDATE clients 
                    SET line_user_id = %s 
                    WHERE id = %s
                """, (line_user_id, client_id))
                print(f"[API Bind] Conditional write success: client_id={client_id} bound to line_user_id={line_user_id}")
            else:
                # 已經綁定過了，且 ID 相同，不需要重複寫入
                print(f"[API Bind] Skipped write: client_id={client_id} already bound to current line_user_id")
            
            # 3. 查詢該客戶最新日期建立的一筆訂單 (依 created_at 與 id 降序)
            cursor.execute("""
                SELECT id FROM orders 
                WHERE client_id = %s 
                ORDER BY created_at DESC, id DESC LIMIT 1
            """, (client_id,))
            order = cursor.fetchone()
            
            order_id = order["id"] if order else None
            
            # 4. 寫入一條 pending 的 LINE 推播訊息告知綁定成功與最新訂單編號
            success_msg = f"【系統通知】\n服務綁定與查詢成功！您的 LINE 帳號已連結至客戶「{db_name}」的登記資料。\n"
            if order_id:
                success_msg += f"您目前最新日期的服務訂單編號為：#{order_id}。\n"
            else:
                success_msg += "目前尚未建立您的案件訂單，行政專員核對名冊後將自動為您建立，請稍候。\n"
            success_msg += "後續有最新媒合進度或排班通知，系統將會主動為您推播。"
            
            cursor.execute("""
                INSERT INTO line_push_tasks (to_user_id, message_content, status)
                VALUES (%s, %s, 'pending')
            """, (line_user_id, success_msg))
            
            conn.commit()
            print(f"[API Bind] Successfully processed client_id={client_id} for line_user_id={line_user_id}. Order ID: {order_id}")
            
            return {
                "status": "success",
                "message": "綁定與查詢成功！",
                "client_name": db_name,
                "client_id": client_id,
                "order_id": order_id
            }
    except Exception as e:
        conn.rollback()
        print(f"[API Bind] Binding process failed: {e}")
        return {
            "status": "error",
            "message": f"伺服器錯誤：{str(e)}"
        }
    finally:
        conn.close()

from typing import Optional, Dict, Any

class LineRegisterPayload(BaseModel):
    name: str
    phone: str
    expected_date: str
    service_days: int
    address: str
    line_user_id: str
    id_number: Optional[str] = ""
    birth_date: Optional[str] = ""
    gender: Optional[str] = ""
    email: Optional[str] = ""
    tel: Optional[str] = ""
    ext: Optional[str] = ""
    city: Optional[str] = ""
    zip_code: Optional[str] = ""
    survey_details: Dict[str, Any] = {}


@app.get("/api/config/liff")
async def get_liff_config():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "liff_settings.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/line/register")
async def line_register(payload: LineRegisterPayload):
    name = payload.name.strip()
    phone = payload.phone.strip()
    line_user_id = payload.line_user_id.strip()
    
    normalized_phone = phone.replace(" ", "").replace("-", "")
    
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. 寫入 clients
            cursor.execute("""
                INSERT INTO clients (name, phone, address, service_days, due_month, line_user_id, gender, city)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (name, normalized_phone, payload.address, payload.service_days, payload.expected_date, line_user_id, payload.gender, payload.city))
            client_id = conn.insert_id()
            
            # 2. 寫入 orders
            cursor.execute("""
                INSERT INTO orders (client_id)
                VALUES (%s)
            """, (client_id,))
            order_id = conn.insert_id()
            
            # 3. 寫入 beclass_records 確保後台查詢一致性
            final_survey = payload.survey_details.copy()
            final_survey["預產期"] = payload.expected_date
            final_survey["預計服務天數"] = payload.service_days
            final_survey["身分證字號"] = payload.id_number
            final_survey["資料來源"] = "LINE 原生表單"
            
            survey_details_json = json.dumps(final_survey, ensure_ascii=False)
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO beclass_records (name, gender, email, birth_date, phone, tel, ext, city, zip_code, address, created_at, survey_details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (name, payload.gender, payload.email, payload.birth_date if payload.birth_date else None, normalized_phone, payload.tel, payload.ext, payload.city, payload.zip_code, payload.address, now_str, survey_details_json))
            
            # 4. 寫入推播任務
            success_msg = f"【系統通知】\n服務登記與綁定成功！\n您的 LINE 帳號已連結至客戶「{name}」的專屬資料庫。\n"
            success_msg += f"您剛建立的服務訂單編號為：#{order_id}。\n"
            success_msg += "工會行政專員將於上班時間透過 LINE 與您聯繫確認服務細節，請您耐心等候！"
            
            cursor.execute("""
                INSERT INTO line_push_tasks (to_user_id, message_content, status)
                VALUES (%s, %s, 'pending')
            """, (line_user_id, success_msg))
            
            conn.commit()
            return {
                "status": "success",
                "client_id": client_id,
                "client_name": name,
                "order_id": order_id
            }
    except Exception as e:
        conn.rollback()
        print(f"[API Register] Error: {e}")
        return {"status": "error", "message": f"建檔失敗: {str(e)}"}
    finally:
        conn.close()

@app.get("/")
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

@app.post("/")
async def root_post(payload: dict, request: Request):
    if "events" in payload:
        print("[LINE Webhook] 警告：收到發送至根目錄 (/) 的 Webhook 請求。自動轉發至 line_webhook 處理。")
        try:
            parsed_payload = LineWebhookPayload(**payload)
            return await line_webhook(parsed_payload, request)
        except Exception as e:
            print(f"[LINE Webhook] 根目錄 Webhook 轉發解析失敗: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "active", "message": "Root POST active"}

@app.get("/liff-page")
@app.get("/gateway")
async def serve_gateway_page():
    """前導選擇頁面 (自動相容舊版 LIFF 設定)"""
    return FileResponse("line/static/gateway.html")

@app.get("/bind-page")
async def serve_bind_page():
    """提供舊客查詢與綁定專用的路徑"""
    return FileResponse("line/static/bind.html")

@app.get("/register-page")
async def serve_register_page():
    """全新客戶原生註冊頁面"""
    return FileResponse("line/static/register.html")

# ----------------- 1. LINE WEBHOOK 接收 -----------------
class LineWebhookPayload(BaseModel):
    events: list = []
    destination: str = ""

@app.get("/webhook/line")
@app.get("/webhook/line/")
@app.get("/webhook")
@app.get("/webhook/")
async def line_webhook_get():
    print("[LINE Webhook] Received GET request (possibly URL verification or redirect)")
    return {"status": "ok", "message": "LINE Webhook endpoint is active"}

@app.post("/webhook/line")
@app.post("/webhook/line/")
@app.post("/webhook")
@app.post("/webhook/")
async def line_webhook(payload: LineWebhookPayload, request: Request):
    print(f"[LINE Webhook] Received line webhook. Events count: {len(payload.events)}")
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for event in payload.events:
                event_type = event.get("type")
                
                # 處理新用戶加入好友 (follow) 事件
                if event_type == "follow":
                    source = event.get("source", {})
                    user_id = source.get("userId", "")
                    print(f"[LINE Webhook] Follow event received from User: {user_id}")
                    
                    if user_id:
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
                        cursor.execute("""
                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                            VALUES (%s, %s, 'pending')
                        """, (user_id, welcome_msg))
                        print(f"[LINE Webhook] Queued welcome message for new user {user_id}")
                
                if event_type == "postback":
                    postback_data = event["postback"].get("data", "")
                    print(f"[LINE Webhook] Postback data received: {postback_data}")
                    
                    params = {}
                    for item in postback_data.split("&"):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            params[k] = v
                            
                    action = params.get("action")
                    order_id = params.get("order_id")
                    staff_id = params.get("staff_id")
                    
                    if not action or not order_id:
                        continue
                        
                    # 月嫂同意
                    if action == "willing":
                        cursor.execute("""
                            UPDATE matching_records 
                            SET caregiver_accepted = 1, replied_at = CURRENT_TIMESTAMP
                            WHERE order_id = %s AND staff_id = %s
                        """, (order_id, staff_id))
                        
                        msg = "感謝您的確認！您已同意接案，工會已將您的履歷推播給客戶，後續有進一步消息會立刻通知您！"
                        cursor.execute("""
                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                            VALUES (COALESCE((SELECT line_user_id FROM staff WHERE id = %s), 'mock_staff_line_id'), %s, 'pending')
                        """, (staff_id, msg))
                        print(f"[LINE Webhook] Caregiver #{staff_id} willing for Order #{order_id}")
                        
                    # 月嫂拒絕
                    elif action == "unwilling":
                        cursor.execute("""
                            UPDATE matching_records 
                            SET caregiver_accepted = 0, replied_at = CURRENT_TIMESTAMP
                            WHERE order_id = %s AND staff_id = %s
                        """, (order_id, staff_id))
                        
                        msg = "已記錄您的回覆，期待下次為您媒合合適的案件！"
                        cursor.execute("""
                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                            VALUES (COALESCE((SELECT line_user_id FROM staff WHERE id = %s), 'mock_staff_line_id'), %s, 'pending')
                        """, (staff_id, msg))
                        print(f"[LINE Webhook] Caregiver #{staff_id} unwilling for Order #{order_id}")
                        
                    # 客戶滿意
                    elif action == "client_approve":
                        cursor.execute("UPDATE orders SET client_approved = 1 WHERE id = %s", (order_id,))
                        
                        msg = "感謝您的確認！行政專員正為您產製電子契約條款，完成後會發送連結至您的 LINE 進行線上簽署。"
                        cursor.execute("""
                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                            VALUES (COALESCE((SELECT line_user_id FROM clients WHERE id = (SELECT client_id FROM orders WHERE id = %s)), 'mock_client_line_id'), %s, 'pending')
                        """, (order_id, msg))
                        print(f"[LINE Webhook] Client approved resume for Order #{order_id}")
                        
                    # 客戶拒絕
                    elif action == "client_reject":
                        cursor.execute("UPDATE orders SET client_approved = 2 WHERE id = %s", (order_id,))
                        
                        msg = "已收到您的回饋，工會將為您重新進行媒合篩選，請稍候。"
                        cursor.execute("""
                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                            VALUES (COALESCE((SELECT line_user_id FROM clients WHERE id = (SELECT client_id FROM orders WHERE id = %s)), 'mock_client_line_id'), %s, 'pending')
                        """, (order_id, msg))
                        print(f"[LINE Webhook] Client rejected resume for Order #{order_id}")
                
                # 處理文字對答與 RAG
                elif event_type == "message":
                    message = event.get("message", {})
                    if message.get("type") == "text":
                        user_text = message.get("text", "")
                        source = event.get("source", {})
                        user_id = source.get("userId", "")
                        reply_token = event.get("replyToken", "")
                        print(f"[LINE Webhook] Text message received from {user_id}: {user_text}")
                        
                        # 攔截「我是月嫂」關鍵字切換選單
                        if "我是月嫂" in user_text:
                            caregiver_menu_id = get_setting("caregiver_rich_menu_id", "")
                            if caregiver_menu_id:
                                line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or get_setting("line_channel_access_token")
                                headers = {"Authorization": f"Bearer {line_token}"}
                                res = requests.post(f"https://api.line.me/v2/bot/user/{user_id}/richmenu/{caregiver_menu_id}", headers=headers)
                                
                                if res.status_code == 200:
                                    replies = load_webhook_replies()
                                    reply_msg = replies.get("caregiver_switch_success")
                                else:
                                    replies = load_webhook_replies()
                                    reply_msg = replies.get("caregiver_switch_fail").replace("{status_code}", str(res.status_code))
                            else:
                                replies = load_webhook_replies()
                                reply_msg = replies.get("caregiver_menu_not_set")
                                
                            cursor.execute("""
                                INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                VALUES (%s, %s, 'pending')
                            """, (user_id, reply_msg))
                            print(f"[LINE Webhook] Intercepted keyword '{user_text}', switched Rich Menu for User: {user_id}")
                            continue
                            
                        # 攔截「esc」關鍵字恢復預設選單
                        if user_text.lower().strip() == "esc":
                            line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or get_setting("line_channel_access_token")
                            headers = {"Authorization": f"Bearer {line_token}"}
                            # 呼叫 DELETE 移除使用者的個人化選單，自動退回系統預設選單
                            res = requests.delete(f"https://api.line.me/v2/bot/user/{user_id}/richmenu", headers=headers)
                            
                            if res.status_code == 200:
                                replies = load_webhook_replies()
                                reply_msg = replies.get("esc_success")
                            else:
                                replies = load_webhook_replies()
                                reply_msg = replies.get("esc_fail").replace("{status_code}", str(res.status_code))
                                
                            cursor.execute("""
                                INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                VALUES (%s, %s, 'pending')
                            """, (user_id, reply_msg))
                            print(f"[LINE Webhook] Intercepted keyword '{user_text}', unlinked Rich Menu for User: {user_id}")
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
                                
                            replies = load_webhook_replies()
                            reply_msg = replies.get("bind_link_msg").replace("{bind_url}", bind_url)
                            
                            cursor.execute("""
                                INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                VALUES (%s, %s, 'pending')
                            """, (user_id, reply_msg))
                            print(f"[LINE Webhook] Intercepted keyword '{user_text}', queued query link for User: {user_id}")
                            continue
                        
                        # 動態取得 RAG 設定與初始化 ChromaDB
                        import chromadb
                        mode = get_setting("embedding_mode", "default")
                        embedding_function = None
                        try:
                            if mode == "openai":
                                import chromadb.utils.embedding_functions as embedding_functions
                                api_key = get_setting("openai_api_key", "")
                                if api_key:
                                    embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                                        api_key=api_key,
                                        model_name="text-embedding-3-small"
                                    )
                            elif mode == "local":
                                import chromadb.utils.embedding_functions as embedding_functions
                                embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                                    model_name="shibing624/text2vec-base-chinese"
                                )
                        except ImportError:
                            pass
                            
                        # 連線至 ChromaDB
                        try:
                            client = chromadb.PersistentClient(path="./db/chroma_data")
                            if embedding_function:
                                collection = client.get_or_create_collection("union_faq", embedding_function=embedding_function)
                            else:
                                collection = client.get_or_create_collection("union_faq")
                                
                            # 如果資料庫為空，可能出現 ValueError，用 try-except 包裝查詢
                            reply_msg = "很抱歉，我不太懂您的意思，已經幫您轉交給行政專員為您人工處理。"
                            try:
                                results = collection.query(
                                    query_texts=[user_text],
                                    n_results=1
                                )
                                if results and results['distances'] and len(results['distances'][0]) > 0:
                                    distance = results['distances'][0][0]
                                    if distance < 1.0: # 依據模型可調整閾值
                                        reply_msg = results['metadatas'][0][0].get("answer", reply_msg)
                            except Exception as query_e:
                                print(f"[LINE Webhook] ChromaDB Query Error (Empty DB?): {query_e}")
                            
                            # 決定回覆模式
                            reply_mode = get_setting("line_reply_mode", "push_daemon")
                            if reply_mode == "reply_sdk":
                                try:
                                    from linebot import LineBotApi
                                    from linebot.models import TextSendMessage
                                    token = get_setting("line_channel_access_token", "")
                                    if token and reply_token:
                                        line_bot_api = LineBotApi(token)
                                        line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_msg))
                                        print("[LINE Webhook] SDK Replied.")
                                        continue
                                except Exception as e:
                                    print(f"[LINE Webhook] SDK Reply Failed: {e}, falling back to push.")
                                    
                            # Fallback to Push Daemon
                            if user_id:
                                cursor.execute("""
                                    INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                    VALUES (%s, %s, 'pending')
                                """, (user_id, reply_msg))
                                print(f"[LINE Webhook] Queued push message for {user_id}")
                            
                        except Exception as e:
                            print(f"[LINE Webhook] RAG Processing Error: {e}")

                        
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[LINE Webhook] Webhook handler failed: {e}")
    finally:
        conn.close()
        
    return {"status": "ok"}

# ----------------- 2. 好好簽 WEBHOOK 接收 -----------------
class BreezySignWebhookPayload(BaseModel):
    event: str
    contract_id: str
    status: str
    signed_at: str = ""

@app.post("/webhook/breezysign")
async def breezysign_webhook(payload: BreezySignWebhookPayload):
    print(f"[Breezy Webhook] Received webhook for contract {payload.contract_id} with status {payload.status}")
    
    if payload.status in ["completed", "signed"]:
        conn = get_db_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("""
                    SELECT o.*, c.name as client_name, c.service_days, c.due_month, c.service_start_date,
                           s.weekly_rest_days, s.name as staff_name
                    FROM orders o
                    JOIN clients c ON o.client_id = c.id
                    LEFT JOIN staff s ON o.staff_id = s.id
                    WHERE o.contract_id = %s
                """, (payload.contract_id,))
                ord = cursor.fetchone()
                
                if ord:
                    order_id = ord["id"]
                    staff_id = ord["staff_id"]
                    client_id = ord["client_id"]
                    service_days = ord["service_days"] if ord["service_days"] else 24
                    
                    print(f"[Breezy Webhook] Found order #{order_id}, triggering auto schedule refiner for {ord['staff_name']}")
                    
                    start_d = ord["actual_start_date"]
                    if not start_d:
                        start_d = date.today() + timedelta(days=10)
                        
                    rest_days = []
                    if ord["weekly_rest_days"]:
                        try:
                            rest_days = json.loads(ord["weekly_rest_days"]) if isinstance(ord["weekly_rest_days"], str) else ord["weekly_rest_days"]
                        except Exception:
                            rest_days = []
                            
                    # 自動執行天數精算順延
                    schedule_res = calculate_attendance_schedule(
                        start_d, service_days, "週休1日", rest_days, set()
                    )
                    end_d = schedule_res.get('actual_end_date')
                    
                    # 更新狀態
                    cursor.execute("""
                        UPDATE orders 
                        SET status = '訂單成立', actual_start_date = %s, actual_end_date = %s, service_mode = '週休 1 日'
                        WHERE id = %s
                    """, (start_d, end_d, order_id))
                    
                    # 清除舊排班
                    cursor.execute("DELETE FROM staff_bookings WHERE staff_id = %s AND client_id = %s", (staff_id, client_id))
                    
                    refined_details = schedule_res.get('day_by_day', [])
                    # 寫入工作日排班
                    for day in refined_details:
                        d_date = day["date"]
                        if day["is_work_day"]:
                            cursor.execute("""
                                INSERT INTO staff_bookings (staff_id, client_id, start_date, end_date)
                                VALUES (%s, %s, %s, %s)
                            """, (staff_id, client_id, d_date, d_date))
                            
                    # 發送 LINE 訊息 (移除 emoji 以免 CP950 錯誤)
                    client_msg = f"恭喜！您與月嫂 {ord['staff_name']} 的服務契約已線上簽署完畢！系統已自動為您登載排班出勤。實際服務區間為：{start_d.strftime('%Y-%m-%d')} ~ {end_d.strftime('%Y-%m-%d')}。"
                    cursor.execute("""
                        INSERT INTO line_push_tasks (to_user_id, message_content, status)
                        VALUES (COALESCE((SELECT line_user_id FROM clients WHERE id = %s), 'mock_client_line_id'), %s, 'pending')
                    """, (client_id, client_msg))
                    
                    staff_msg = f"恭喜！您與客戶 {ord['client_name']} 的服務合約已完成線上簽署！系統已為您登載排班日程：{start_d.strftime('%Y-%m-%d')} ~ {end_d.strftime('%Y-%m-%d')}，請做好服務準備。"
                    cursor.execute("""
                        INSERT INTO line_push_tasks (to_user_id, message_content, status)
                        VALUES (COALESCE((SELECT line_user_id FROM staff WHERE id = %s), 'mock_staff_line_id'), %s, 'pending')
                    """, (staff_id, staff_msg))
                    
                    conn.commit()
                    print(f"[Breezy Webhook] Order #{order_id} processed. Schedule set to {start_d} ~ {end_d}")
            
        except Exception as e:
            conn.rollback()
            print(f"[Breezy Webhook] Failed to process webhook: {e}")
        finally:
            conn.close()
            
    return {"status": "success"}


# ==========================================
# 🔌 GitHub 整合路由 (RESTful Endpoints)
# ==========================================
from fastapi.middleware.cors import CORSMiddleware
from api.routes import orders, matches, schedule, payments, clients, staff, holidays
from fastapi.responses import RedirectResponse
from api.schemas.base import BaseResponse

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")

@app.get("/health", response_model=BaseResponse[dict], tags=["Health"])
def health_check():
    return BaseResponse(data={"status": "healthy", "service": "Lobar Union API"}, message="API Server is running normally")

# 註冊業務模組 Routers
app.include_router(orders.router)
app.include_router(matches.router)
app.include_router(schedule.router)
app.include_router(payments.router)
app.include_router(clients.router)
app.include_router(staff.router)
app.include_router(holidays.router)

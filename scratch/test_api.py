# -*- coding: utf-8 -*-
import os
import sys
import requests
import pymysql
import json
import time

# 確保可以載入 admin.utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from admin.utils import get_db_connection

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=== Start End-to-End Integration Tests (Updated) ===")
    
    # 測試端點 1: Health check
    try:
        res = requests.get(f"{BASE_URL}/")
        print(f"Health check status: {res.status_code}, content: {res.json()}")
    except Exception as e:
        print(f"FastAPI server not available: {e}")
        return
        
    # 清除之前的測試殘留與設定測試狀態
    conn = get_db_connection()
    test_client_id = None
    try:
        with conn.cursor() as cursor:
            # 清除 line_push_tasks 內相關測試帳號
            cursor.execute("DELETE FROM line_push_tasks WHERE to_user_id = 'Utest123'")
            
            # 確保存在測試用客戶「張三」（電話：0912345678）
            cursor.execute("SELECT id FROM clients WHERE name='張三' AND phone='0912345678'")
            client = cursor.fetchone()
            if client:
                test_client_id = client[0]
                # 重設其 line_user_id 為 NULL 進行條件寫入測試
                cursor.execute("UPDATE clients SET line_user_id = NULL WHERE id = %s", (test_client_id,))
            else:
                cursor.execute("INSERT INTO clients (name, phone, case_no) VALUES ('張三', '0912345678', '115000099')")
                test_client_id = conn.insert_id()
                
            # 清除該客戶之既有訂單，並重新建立兩筆（一舊一新）以測試「最新訂單編號」
            cursor.execute("DELETE FROM orders WHERE client_id = %s", (test_client_id,))
            
            # 第一筆舊訂單
            cursor.execute("""
                INSERT INTO orders (client_id, status, created_at)
                VALUES (%s, '洽談中', DATE_SUB(NOW(), INTERVAL 1 DAY))
            """, (test_client_id,))
            old_order_id = conn.insert_id()
            
            # 第二筆最新訂單
            cursor.execute("""
                INSERT INTO orders (client_id, status, created_at)
                VALUES (%s, '洽談中', NOW())
            """, (test_client_id,))
            new_order_id = conn.insert_id()
            
            conn.commit()
            print(f"Database test state initialized. Client ID: {test_client_id}, Old Order ID: {old_order_id}, New Order ID: {new_order_id}")
    finally:
        conn.close()

    # 1. 測試 LINE Webhook - follow 事件
    print("\n--- Test Case 1: Send follow webhook event ---")
    follow_payload = {
        "events": [
            {
                "type": "follow",
                "replyToken": "test_reply_token_123",
                "source": {
                    "userId": "Utest123",
                    "type": "user"
                },
                "timestamp": 1625682000000,
                "mode": "active"
            }
        ],
        "destination": "Udestination123"
    }
    
    webhook_res = requests.post(f"{BASE_URL}/webhook/line", json=follow_payload)
    print(f"Webhook response status: {webhook_res.status_code}, content: {webhook_res.json()}")
    
    # 驗證資料庫是否寫入 follow push task
    time.sleep(0.5)
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM line_push_tasks WHERE to_user_id = 'Utest123' ORDER BY id DESC LIMIT 1")
            task = cursor.fetchone()
            if task:
                print(f"Success! Found follow push task: ID {task['id']}")
                if "/gateway" in task['message_content'] and "Utest123" in task['message_content']:
                    print("Verification PASSED: Welcome message contains the correct binding link.")
                else:
                    print("Verification FAILED: Link template mismatch.")
            else:
                print("Verification FAILED: No push task found for Utest123.")
    finally:
        conn.close()

    # 2. 測試 LINE Webhook - message 事件 (輸入「查詢訂單編號」關鍵字)
    print("\n--- Test Case 2: Send keyword '我要查詢訂單編號' webhook event ---")
    msg_payload = {
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "msg_99999",
                    "text": "我要查詢訂單編號"
                },
                "source": {
                    "userId": "Utest123",
                    "type": "user"
                },
                "replyToken": "reply_token_999",
                "timestamp": 1625682000000,
                "mode": "active"
            }
        ]
    }
    
    msg_res = requests.post(f"{BASE_URL}/webhook/line", json=msg_payload)
    print(f"Message webhook status: {msg_res.status_code}")
    
    # 驗證是否寫入針對關鍵字回覆之推播
    time.sleep(0.5)
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM line_push_tasks WHERE to_user_id = 'Utest123' ORDER BY id DESC LIMIT 1")
            task = cursor.fetchone()
            if task and "進行訂單查詢與帳號綁定" in task['message_content']:
                print(f"Success! Intercepted keyword and found query task: ID {task['id']}")
                print("Verification PASSED: Keyword query flow works correctly.")
            else:
                print("Verification FAILED: Keyword flow did not output correct response.")
    finally:
        conn.close()

    # 3. 測試 帳號綁定/查詢 API (第一次綁定：條件寫入)
    print("\n--- Test Case 3: Bind client and fetch latest order (First Bind) ---")
    bind_payload = {
        "name": "張三",
        "phone": "0912345678",
        "line_user_id": "Utest123"
    }
    
    bind_res = requests.post(f"{BASE_URL}/api/line/bind", json=bind_payload)
    print(f"Bind API response: {json.dumps(bind_res.json(), ensure_ascii=False, indent=2)}")
    
    # 驗證資料庫條件寫入結果與抓取之訂單編號
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 檢查 clients
            cursor.execute("SELECT line_user_id FROM clients WHERE id = %s", (test_client_id,))
            client = cursor.fetchone()
            if client and client['line_user_id'] == 'Utest123':
                print("Verification PASSED: line_user_id conditionally written because it was NULL.")
            else:
                print("Verification FAILED: line_user_id was not written.")
            
            # 檢查回傳的訂單編號是否為新訂單
            res_json = bind_res.json()
            if res_json.get("order_id") == new_order_id:
                print(f"Verification PASSED: Fetched latest Order ID: {new_order_id} (ignoring old Order ID: {old_order_id})")
            else:
                print(f"Verification FAILED: Fetched Order ID was {res_json.get('order_id')}, expected {new_order_id}.")
                
            # 檢查產生的成功推播
            cursor.execute("""
                SELECT * FROM line_push_tasks 
                WHERE to_user_id = 'Utest123' AND message_content LIKE '%服務綁定與查詢成功%' 
                ORDER BY id DESC LIMIT 1
            """)
            success_task = cursor.fetchone()
            if success_task and f"#{new_order_id}" in success_task['message_content']:
                print("Verification PASSED: Success notification contains the latest order ID.")
            else:
                print("Verification FAILED: Success notification was incorrect or not found.")
    finally:
        conn.close()

    # 4. 測試 帳號綁定/查詢 API (第二次查詢：有新訂單，但 line_user_id 已有值)
    print("\n--- Test Case 4: Query latest order for already bound client ---")
    
    # 建立第三筆更新日期的訂單
    conn = get_db_connection()
    third_order_id = None
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO orders (client_id, status, created_at)
                VALUES (%s, '洽談中', NOW())
            """, (test_client_id,))
            third_order_id = conn.insert_id()
            conn.commit()
            print(f"Created a new order #{third_order_id} for already bound client.")
    finally:
        conn.close()
        
    # 發送相同的請求模擬查詢
    query_res = requests.post(f"{BASE_URL}/api/line/bind", json=bind_payload)
    print(f"Query API response: {json.dumps(query_res.json(), ensure_ascii=False, indent=2)}")
    
    # 驗證回傳的最新訂單
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 驗證 line_user_id 維持不變
            cursor.execute("SELECT line_user_id FROM clients WHERE id = %s", (test_client_id,))
            client = cursor.fetchone()
            if client and client['line_user_id'] == 'Utest123':
                print("Verification PASSED: line_user_id kept unchanged.")
            else:
                print("Verification FAILED: line_user_id check failed.")
                
            # 驗證回傳的最新訂單 ID 為 third_order_id
            q_json = query_res.json()
            if q_json.get("order_id") == third_order_id:
                print(f"Verification PASSED: Correctly returned the third latest Order ID: {third_order_id}")
            else:
                print(f"Verification FAILED: Returned Order ID {q_json.get('order_id')}, expected {third_order_id}")
    finally:
        conn.close()

    # 5. 測試 重複綁定防護與強制重新綁定 (Rebind Confirmation)
    print("\n--- Test Case 5: Rebind Confirmation with different userId ---")
    
    # 模擬換了新帳號，傳入不同的 line_user_id
    rebind_payload = {
        "name": "張三",
        "phone": "0912345678",
        "line_user_id": "Unewfake123"
    }
    
    # 第一次請求（未帶 force_rebind），應該要被擋下並回傳 confirm_rebind
    rebind_res_1 = requests.post(f"{BASE_URL}/api/line/bind", json=rebind_payload)
    res_1_json = rebind_res_1.json()
    print(f"Rebind attempt 1 response: {res_1_json}")
    if res_1_json.get("status") == "confirm_rebind":
        print("Verification PASSED: Server detected mismatched userId and asked for confirmation.")
    else:
        print("Verification FAILED: Server did not return confirm_rebind status.")
        
    # 第二次請求（帶上 force_rebind=True），應該要覆蓋並成功
    rebind_payload["force_rebind"] = True
    rebind_res_2 = requests.post(f"{BASE_URL}/api/line/bind", json=rebind_payload)
    res_2_json = rebind_res_2.json()
    print(f"Rebind attempt 2 response: {res_2_json}")
    if res_2_json.get("status") == "success":
        print("Verification PASSED: Server accepted forced rebind.")
    else:
        print("Verification FAILED: Server rejected forced rebind.")
        
    # 檢查資料庫是否真的被覆蓋
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT line_user_id FROM clients WHERE id = %s", (test_client_id,))
            client = cursor.fetchone()
            if client and client['line_user_id'] == 'Unewfake123':
                print("Verification PASSED: line_user_id was successfully overwritten with new ID.")
            else:
                print("Verification FAILED: line_user_id was NOT overwritten in database.")
    finally:
        conn.close()

    # 6. 測試原生表單註冊 (Native Form Registration)
    print("\n--- Test Case 6: Native Registration Form ---")
    register_payload = {
        "name": "李四",
        "phone": "0987654321",
        "expected_date": "2026-10-01",
        "service_days": 30,
        "address": "新竹市東區某某路123號",
        "line_user_id": "UNewUser456",
        "gender": "女",
        "id_number": "A123456789",
        "email": "test@example.com",
        "city": "新竹市",
        "zip_code": "300",
        "survey_details": {
            "月子餐點調理喜好/飲食習慣：": "葷食",
            "3．料理用油：(可接受種類)": "麻油(後兩週), 苦茶油(前兩週)",
            "哺乳方式：": "母乳",
            "※已確實詳閱退費原則：": "Y"
        }
    }
    register_res = requests.post(f"{BASE_URL}/api/line/register", json=register_payload)
    print(f"Register API response: {register_res.json()}")
    
    if register_res.status_code == 200 and register_res.json().get("status") == "success":
        new_client_id = register_res.json().get("client_id")
        new_order_id = register_res.json().get("order_id")
        print("Verification PASSED: Registration successful.")
        
        # 驗證資料庫寫入狀況
        conn = get_db_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT * FROM clients WHERE id = %s", (new_client_id,))
                client_db = cursor.fetchone()
                if client_db and client_db["name"] == "李四" and client_db["line_user_id"] == "UNewUser456":
                    print("Verification PASSED: Client data fully written to DB.")
                
                cursor.execute("SELECT * FROM orders WHERE id = %s", (new_order_id,))
                order_db = cursor.fetchone()
                if order_db and order_db["client_id"] == new_client_id:
                    print("Verification PASSED: Initial order successfully created.")
                    
                cursor.execute("SELECT * FROM beclass_records WHERE name = %s ORDER BY id DESC LIMIT 1", ("李四",))
                beclass_db = cursor.fetchone()
                if beclass_db and beclass_db["address"] == "新竹市東區某某路123號" and "2026-10-01" in beclass_db["survey_details"]:
                    print("Verification PASSED: beclass_records successfully synced for compatibility.")
        finally:
            conn.close()
    else:
        print("Verification FAILED: Registration API failed.")

if __name__ == "__main__":
    run_tests()

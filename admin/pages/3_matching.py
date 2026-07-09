# -*- coding: utf-8 -*-
"""
File: admin/pages/3_🤝_matching.py
Description: 頁面三：🤝 案件與配對中心 (Clients, Orders & Matching)
"""
import streamlit as st
import pymysql
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 動態設定 sys.path 確保能定位到 admin.utils
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from admin.utils import get_db_connection

# 載入環境變數
load_dotenv()

st.set_page_config(
    page_title="案件與配對中心 - 月子工會系統",
    page_icon="🤝",
    layout="wide"
)

# 嵌入客製化 CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Microsoft JhengHei', sans-serif;
    }
    
    .page-title {
        background: linear-gradient(135deg, #3A7BD5 0%, #00D2FF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
    
    .workflow-step {
        background: #F7FAFC;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        border-left: 4px solid #3A7BD5;
    }
</style>
""", unsafe_allow_html=True)


# 載入訂單列表
def load_orders(search_query="", status_filter="所有狀態"):
    conn = get_db_connection()
    orders = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT o.*, c.name as client_name, c.phone as client_phone, c.due_month, c.notes as client_notes,
                       s.name as staff_name
                FROM orders o
                JOIN clients c ON o.client_id = c.id
                LEFT JOIN staff s ON o.staff_id = s.id
                WHERE 1=1
            """
            params = []
            if search_query:
                sql += " AND (c.name LIKE %s OR c.phone LIKE %s OR o.id = %s)"
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_query])
                
            if status_filter != "所有狀態":
                sql += " AND o.status = %s"
                params.append(status_filter)
                
            sql += " ORDER BY o.id DESC"
            cursor.execute(sql, tuple(params))
            orders = cursor.fetchall()
    finally:
        conn.close()
    return orders

# 頁面主體渲染
st.markdown('<h1 class="page-title">🤝 案件與配對中心</h1>', unsafe_allow_html=True)

# 頂部搜尋與過濾
col_s1, col_s2 = st.columns([2, 1])
with col_s1:
    search_query = st.text_input("🔍 搜尋客戶姓名 / 電話 / 訂單編號：", value="")
with col_s2:
    status_filter = st.selectbox("篩選狀態：", ["所有狀態", "洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"])

orders = load_orders(search_query, status_filter)

# 顯示訂單列表
if not orders:
    st.info("💡 找不到符合條件的案件訂單。")
else:
    # 轉換成 Pandas 展示以防 Streamlit 重新載入，並使用 Columns 手動展示以提供互動按鈕
    for o in orders:
        with st.container():
            # 卡片框線美化
            status_color = "#3182CE" # 預設藍
            if o["status"] == "洽談中": status_color = "#E53E3E" # 紅
            elif o["status"] == "服務中": status_color = "#48BB78" # 綠
            elif o["status"] == "訂單完成": status_color = "#805AD5" # 紫
            elif o["status"] == "訂單取消": status_color = "#A0AEC0" # 灰
            
            st.markdown(f"""
            <div style="border: 1px solid #E2E8F0; border-left: 6px solid {status_color}; border-radius: 8px; padding: 15px; margin-bottom: 15px; background: white;">
                <span style="font-weight:bold; font-size: 1.1rem; color: #2D3748;">訂單 ID: #{o['id']} ｜ 客戶: {o['client_name']} ({o['client_phone']})</span><br/>
                <span style="color: #718096; font-size: 0.9rem;">預產期: {o['due_month']} ｜ 指派人員: {o['staff_name'] if o['staff_name'] else '❌ 尚未指派'} ｜ 目前狀態: <strong>{o['status']}</strong></span>
            </div>
            """, unsafe_allow_html=True)
            
            # 操作按鈕列
            col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
            
            with col_b1:
                show_details = st.button(f"👁️ 檢視詳情", key=f"details_{o['id']}")
            with col_b2:
                # 只有洽談中可以點配對
                allow_match = o["status"] == "洽談中"
                show_match = st.button(f"⚡ 智慧配對", key=f"match_{o['id']}", disabled=not allow_match)
            with col_b3:
                # 洽談中推進到訂單成立 (確認收訂金)
                allow_deposit = o["status"] == "洽談中"
                confirm_deposit = st.button(f"💰 確認收訂金", key=f"dep_{o['id']}", disabled=not allow_deposit)
            with col_b4:
                # 訂單成立推進到服務中，服務中推進到訂單完成 (確認收尾款)
                allow_final = o["status"] in ["訂單成立", "服務中"]
                confirm_final = st.button(f"💵 確認收尾款", key=f"fin_{o['id']}", disabled=not allow_final)
            with col_b5:
                # 只要未結案皆可取消
                allow_cancel = o["status"] not in ["訂單完成", "訂單取消"]
                confirm_cancel = st.button(f"❌ 取消案件", key=f"cancel_{o['id']}", disabled=not allow_cancel)

            # --- 按鈕邏輯處理 ---
            if show_details:
                st.info(f"📋 **BeClass 客戶需求與問卷細節**")
                # 嘗試讀取 beclass 或是 notes
                conn = get_db_connection()
                try:
                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute("SELECT * FROM beclass_records WHERE name = %s", (o["client_name"],))
                        beclass = cursor.fetchone()
                        if beclass and beclass["survey_details"]:
                            st.json(json.loads(beclass["survey_details"]))
                        else:
                            st.write(f"備註/其他事項: {o['client_notes'] if o['client_notes'] else '無'}")
                finally:
                    conn.close()
            
            if confirm_deposit:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        # 推進訂單狀態
                        cursor.execute("UPDATE orders SET status = '訂單成立' WHERE id = %s", (o["id"],))
                        # 新增/更新 payments 對帳
                        cursor.execute("""
                            INSERT INTO payments (order_id, case_no, client_name, deposit_received, deposit_received_at, payment_status)
                            VALUES (%s, (SELECT case_no FROM clients WHERE id=%s), %s, 12000.0, CURDATE(), '已收訂金')
                            ON DUPLICATE KEY UPDATE deposit_received=12000.0, deposit_received_at=CURDATE(), payment_status='已收訂金'
                        """, (o["id"], o["client_id"], o["client_name"]))
                        conn.commit()
                        st.success(f"🎉 訂單 #{o['id']} 已成功收款訂金，狀態更新為「訂單成立」！")
                        st.rerun()
                except Exception as err:
                    conn.rollback()
                    st.error(f"資料庫更新失敗: {err}")
                finally:
                    conn.close()
                    
            if confirm_final:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("UPDATE orders SET status = '訂單完成' WHERE id = %s", (o["id"],))
                        cursor.execute("""
                            UPDATE payments 
                            SET balance_received = 68000.0, balance_received_at = CURDATE(), payment_status = '已結案'
                            WHERE order_id = %s
                        """, (o["id"],))
                        conn.commit()
                        st.success(f"🎉 訂單 #{o['id']} 已成功核銷服務尾款，狀態更新為「訂單完成 (已結案)」！")
                        st.rerun()
                except Exception as err:
                    conn.rollback()
                    st.error(f"資料庫更新失敗: {err}")
                finally:
                    conn.close()

            if confirm_cancel:
                st.warning(f"⚠️ **您正在取消訂單 #{o['id']}**")
                with st.form(key=f"cancel_form_{o['id']}"):
                    cancel_reason = st.text_area("請輸入取消原因 (必填)：", value="")
                    submit_cancel = st.form_submit_button("💾 確認取消")
                    
                    if submit_cancel:
                        if not cancel_reason.strip():
                            st.error("❌ 取消原因不得為空！")
                        else:
                            conn = get_db_connection()
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute("""
                                        UPDATE orders 
                                        SET status = '訂單取消', cancel_reason = %s 
                                        WHERE id = %s
                                    """, (cancel_reason, o["id"]))
                                    conn.commit()
                                    st.info(f"🚫 訂單 #{o['id']} 已成功取消。")
                                    st.rerun()
                            except Exception as err:
                                conn.rollback()
                                st.error(f"更新失敗: {err}")
                            finally:
                                conn.close()
                                
            # --- 展開配對面板 ---
            if show_match:
                st.markdown(f"### ⚡ 訂單 #{o['id']} 智慧配對面板")
                
                # 步驟 1：條件篩選
                st.markdown('<div class="workflow-step"><strong>步驟 1：條件篩選 (Manual Filtering)</strong></div>', unsafe_allow_html=True)
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    f_region = st.checkbox("篩選可承接地區 (符合客戶縣市)", value=True)
                with col_f2:
                    f_skill = st.checkbox("優先篩選有特殊證照的月嫂 (如: 嬰幼兒按摩)", value=False)
                
                # 讀取並篩選符合的月嫂
                conn = get_db_connection()
                staff = []
                try:
                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        sql_s = "SELECT * FROM staff WHERE status='active'"
                        cursor.execute(sql_s)
                        all_staff = cursor.fetchall()
                        
                        for s in all_staff:
                            keep = True
                            # 1. 地區比對
                            if f_region:
                                # 簡化比對：如果客戶居住的新竹市/竹北市有出現在月嫂地址或名稱中
                                if "新竹" not in s["address"] and "竹北" not in s["address"]:
                                    keep = False
                            # 2. 證照比對
                            if f_skill:
                                if not s["has_massage_cert"]:
                                    keep = False
                            if keep:
                                staff.append(s)
                finally:
                    conn.close()
                    
                if not staff:
                    st.warning("⚠️ 找不到符合篩選條件的合格服務人員！")
                else:
                    # 顯示合格月嫂列表
                    staff_rows = []
                    for s in staff:
                        staff_rows.append({
                            "人員 ID": s["id"],
                            "姓名": s["name"],
                            "連絡電話": s["phone"],
                            "按摩證書": "有" if s["has_massage_cert"] else "無",
                            "地址": s["address"]
                        })
                    st.table(staff_rows)
                    
                    # 步驟 2：詢問月嫂意願
                    st.markdown('<div class="workflow-step"><strong>步驟 2：詢問服務人員接案意願 (Caregiver Consent)</strong></div>', unsafe_allow_html=True)
                    selected_match_staff_name = st.selectbox("選擇要詢問的月嫂：", [s["name"] for s in staff], key=f"staff_sel_{o['id']}")
                    
                    match_staff = next(s for s in staff if s["name"] == selected_match_staff_name)
                    
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        send_consent = st.button("💬 一鍵發送 LINE 意願詢問", key=f"send_con_{o['id']}")
                        if send_consent:
                            conn = get_db_connection()
                            try:
                                with conn.cursor() as cursor:
                                    # 寫入 matching_records
                                    cursor.execute("""
                                        INSERT INTO matching_records (order_id, staff_id, caregiver_accepted, sent_at)
                                        VALUES (%s, %s, NULL, NOW())
                                    """, (o["id"], match_staff["id"]))
                                    # 寫入 line_push_tasks 模擬發送
                                    msg_text = f"【派案意願詢問】客戶{o['client_name']}預產期為{o['due_month']}，是否願意接案？"
                                    cursor.execute("""
                                        INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                        VALUES (%s, %s, 'pending')
                                    """, (match_staff["line_user_id"] if match_staff["line_user_id"] else "mock_line_id", msg_text))
                                    conn.commit()
                                    st.success(f"📬 已向月嫂 {match_staff['name']} 發送意願詢問通知 (任務已寫入 line_push_tasks)！")
                            except Exception as err:
                                conn.rollback()
                                st.error(f"發送失敗: {err}")
                            finally:
                                conn.close()
                                
                    with col_m2:
                        # 測試模擬器
                        st.caption("🧪 測試工具：模擬月嫂回覆")
                        sim_yes = st.button("🟢 模擬月嫂在 LINE 回覆「願意接案」", key=f"sim_yes_{o['id']}")
                        if sim_yes:
                            conn = get_db_connection()
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute("""
                                        UPDATE matching_records 
                                        SET caregiver_accepted = 1, replied_at = NOW()
                                        WHERE order_id = %s AND staff_id = %s
                                    """, (o["id"], match_staff["id"]))
                                    conn.commit()
                                    st.success(f"🧪 模擬成功！月嫂 {match_staff['name']} 接案狀態更新為「願意接案」。")
                                    st.rerun()
                            except Exception as err:
                                conn.rollback()
                                st.error(f"模擬更新失敗: {err}")
                            finally:
                                conn.close()
                                
                    # 步驟 3：傳送履歷給客戶
                    st.markdown('<div class="workflow-step"><strong>步驟 3：履歷預覽與傳送給客戶 (Client Resume Review)</strong></div>', unsafe_allow_html=True)
                    # 讀取已同意的月嫂
                    conn = get_db_connection()
                    accepted_staff = []
                    try:
                        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                            cursor.execute("""
                                SELECT s.* FROM matching_records m
                                JOIN staff s ON m.staff_id = s.id
                                WHERE m.order_id = %s AND m.caregiver_accepted = 1
                            """, (o["id"],))
                            accepted_staff = cursor.fetchall()
                    finally:
                        conn.close()
                        
                    if not accepted_staff:
                        st.caption("*(目前尚無已同意接案的候選月嫂，請先完成步驟 2)*")
                    else:
                        selected_client_staff = st.selectbox("選擇要發送履歷的同意月嫂：", [s["name"] for s in accepted_staff], key=f"client_staff_{o['id']}")
                        target_staff = next(s for s in accepted_staff if s["name"] == selected_client_staff)
                        
                        col_r1, col_r2 = st.columns(2)
                        with col_r1:
                            send_resume = st.button("💬 傳送結構化履歷給客戶 LINE", key=f"send_res_{o['id']}")
                            if send_resume:
                                conn = get_db_connection()
                                try:
                                    with conn.cursor() as cursor:
                                        msg_text = f"【履歷推薦】為您推薦月嫂：{target_staff['name']}。經驗豐富，證照齊全！"
                                        cursor.execute("""
                                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                            VALUES ((SELECT line_user_id FROM clients WHERE id=%s), %s, 'pending')
                                        """, (o["client_id"], msg_text))
                                        conn.commit()
                                        st.success(f"📬 履歷已傳送至客戶 {o['client_name']} 的 LINE 視窗！")
                                except Exception as err:
                                    conn.rollback()
                                    st.error(f"發送失敗: {err}")
                                finally:
                                    conn.close()
                        with col_r2:
                            st.caption("🧪 測試工具：模擬客戶回饋")
                            sim_client_ok = st.button("🟢 模擬客戶在 LINE 回覆「對月嫂滿意」", key=f"sim_c_ok_{o['id']}")
                            if sim_client_ok:
                                conn = get_db_connection()
                                try:
                                    with conn.cursor() as cursor:
                                        cursor.execute("UPDATE orders SET client_approved = 1 WHERE id = %s", (o["id"],))
                                        conn.commit()
                                        st.success("🧪 模擬成功！客戶確認對月嫂滿意，請至步驟 4 編輯並發送合約。")
                                        st.rerun()
                                except Exception as err:
                                    conn.rollback()
                                    st.error(f"模擬更新失敗: {err}")
                                finally:
                                    conn.close()
                                
                    # 步驟 4：合約手動編輯與好好簽 API 整合
                    st.markdown('<div class="workflow-step"><strong>步驟 4：合約手動編輯與電子契約發送 (E-Contract)</strong></div>', unsafe_allow_html=True)
                    
                    # 檢查模擬客戶是否已同意
                    is_approved = (o.get("client_approved") == 1) or (o["status"] in ["訂單成立", "服務中", "訂單完成"])
                    if not is_approved and not accepted_staff:
                        st.caption("*(請先完成步驟 3 客戶確認後方可進行合約編輯)*")
                    else:
                        if not accepted_staff:
                            st.warning("請先選定月嫂並完成步驟 3。")
                        else:
                            # 展開編輯合約
                            with st.form(key=f"contract_form_{o['id']}"):
                                st.markdown("##### ✍️ 編輯電子合約條款")
                                c_client_name = st.text_input("甲方 (客戶姓名)：", value=o["client_name"])
                                c_staff_name = st.text_input("乙方 (月嫂姓名)：", value=selected_client_staff)
                                c_price = st.number_input("總計服務費用 (元)：", min_value=1000, max_value=200000, value=80000)
                                c_days = st.number_input("希望服務天數：", min_value=1, max_value=60, value=24)
                                c_notes = st.text_area("合約特別約定條款：", value="排除固定休假日，服務期滿發放尾款。")
                                
                                submit_contract = st.form_submit_button("⚡ 一鍵送出好好簽電子契約並指派")
                                
                            if submit_contract:
                                # 讀取好好簽環境變數
                                breezy_key = os.getenv("BREEZYSIGN_API_KEY", "your_breezysign_api_key_here")
                                breezy_url = os.getenv("BREEZYSIGN_API_URL", "https://api.breezysign.com/v1")
                                breezy_template_id = os.getenv("BREEZYSIGN_TEMPLATE_ID", "your_breezysign_template_id_here")
                                
                                contract_id = "breezy_mock_99718"
                                sign_url = "https://mock.breezysign.com/sign/99718"
                                is_mock_mode = True
                                
                                if breezy_key and breezy_key != "your_breezysign_api_key_here":
                                    import requests
                                    try:
                                        headers = {
                                            "Authorization": f"Bearer {breezy_key}",
                                            "Content-Type": "application/json"
                                        }
                                        payload = {
                                            "template_id": breezy_template_id,
                                            "contract_name": f"月子照顧服務契約 - {c_client_name}",
                                            "variables": {
                                                "client_name": c_client_name,
                                                "staff_name": c_staff_name,
                                                "price": str(c_price),
                                                "days": str(c_days),
                                                "notes": c_notes
                                            }
                                        }
                                        res = requests.post(f"{breezy_url}/contracts/create-from-template", json=payload, headers=headers, timeout=5)
                                        if res.status_code in [200, 201]:
                                            res_data = res.json()
                                            contract_id = res_data.get("contract_id", "breezy_api_99718")
                                            sign_url = res_data.get("sign_url", f"https://breezysign.com/sign/{contract_id}")
                                            is_mock_mode = False
                                        else:
                                            st.warning(f"⚠️ 好好簽 API 回傳代碼 {res.status_code}，自動切換至模擬模式。")
                                    except Exception as ex:
                                        st.warning(f"⚠️ 好好簽 API 連線失敗 ({ex})，自動切換至模擬模式。")
                                        
                                if is_mock_mode:
                                    st.info("💡 檢測到好好簽 API 金鑰為預設占位符，系統自動啟用【擬真模擬模式】進行合約演示。")
                                    
                                # 好好簽與排班連動
                                conn = get_db_connection()
                                try:
                                    with conn.cursor() as cursor:
                                        # 1. 綁定月嫂至訂單並變更狀態
                                        cursor.execute("""
                                            UPDATE orders 
                                            SET staff_id = %s, contract_id = %s, status = '訂單成立'
                                            WHERE id = %s
                                        """, (target_staff["id"], contract_id, o["id"]))
                                        
                                        # 2. 將合約簽發通知任務寫入 LINE 任務表
                                        msg_text = f"【合約簽署通知】電子合約已建立，請點選連結進行線上簽章：{sign_url}"
                                        cursor.execute("""
                                            INSERT INTO line_push_tasks (to_user_id, message_content, status)
                                            VALUES (COALESCE((SELECT line_user_id FROM staff WHERE id = %s), 'mock_staff_line'), %s, 'pending')
                                        """, (target_staff["id"], msg_text))
                                        
                                        # 3. 模擬自動排班日程寫入 staff_bookings
                                        start_date = datetime.today() + timedelta(days=10)
                                        rest_days_raw = target_staff["weekly_rest_days"]
                                        r_days = []
                                        if rest_days_raw:
                                            r_days = json.loads(rest_days_raw) if isinstance(rest_days_raw, str) else rest_days_raw
                                            
                                        # 兩階段原則：階段一配對簽約時，結束日直接平鋪（不扣除休假）
                                        end_date = start_date + timedelta(days=int(c_days) - 1)
                                        
                                        cursor.execute("""
                                            INSERT INTO staff_bookings (staff_id, client_id, start_date, end_date)
                                            VALUES (%s, %s, %s, %s)
                                        """, (target_staff["id"], o["client_id"], start_date, end_date))
                                        
                                        conn.commit()
                                        st.success(f"🎉 電子契約發送成功！已成功綁定月嫂 {target_staff['name']}，訂單推進至「訂單成立」，且月嫂排班日程 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}) 已自動完成登記！")
                                        st.rerun()
                                except Exception as err:
                                    conn.rollback()
                                    st.error(f"寫入資料庫失敗: {err}")
                                finally:
                                    conn.close()

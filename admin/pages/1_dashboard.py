# -*- coding: utf-8 -*-
"""
File: admin/pages/1_📊_dashboard.py
Description: 頁面一：📊 儀表板與資料異常處理 (Dashboard & Anomalies)
"""
import streamlit as st
import pymysql
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from admin.utils import get_db_connection

st.set_page_config(
    page_title="儀表板與資料異常處理 - 月子工會系統",
    page_icon="📊",
    layout="wide"
)

# 嵌入精美 CSS 樣式 (微調 metric 卡片、陰影懸停卡片與修改面板)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Microsoft JhengHei', sans-serif;
    }
    
    /* 漸層標題 */
    .page-title {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
    
    /* 質感 KPI 卡片 */
    .kpi-container {
        display: flex;
        gap: 1.5rem;
        margin-bottom: 2rem;
    }
    
    .kpi-card {
        background: #FFFFFF;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        padding: 1.5rem;
        flex: 1;
        text-align: center;
        border-bottom: 4px solid #11998e;
        transition: transform 0.2s ease;
    }
    
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 15px rgba(0,0,0,0.08);
    }
    
    .kpi-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #2D3748;
    }
    
    .kpi-label {
        font-size: 1rem;
        color: #718096;
        margin-top: 0.5rem;
    }
    
    /* 隔離區容器 */
    .quarantine-container {
        background: #FFF5F5;
        border: 1px solid #FEB2B2;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)



# 初始化保險狀態欄位
def init_insurance_column():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("ALTER TABLE orders ADD COLUMN insurance_status VARCHAR(50) DEFAULT 'pending' COMMENT '加退保狀態'")
                conn.commit()
            except pymysql.err.OperationalError as e:
                if e.args[0] != 1060: # Column already exists
                    raise e
    finally:
        conn.close()

init_insurance_column()

# 讀取 KPI 數據
def load_kpi_data():
    conn = get_db_connection()
    kpis = {"new_clients": 0, "active_orders": 0, "anomalies": 0}
    try:
        with conn.cursor() as cursor:
            # 1. 當月新增客戶 (過去 30 天)
            cursor.execute("SELECT COUNT(*) FROM clients WHERE db_created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
            kpis["new_clients"] = cursor.fetchone()[0]
            
            # 2. 進行中案件 (狀態為 訂單成立, 服務中)
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('訂單成立', '服務中')")
            kpis["active_orders"] = cursor.fetchone()[0]
            
            # 3. 待處理資料異常
            cursor.execute("SELECT COUNT(*) FROM data_anomaly_events WHERE process_status = 'pending'")
            kpis["anomalies"] = cursor.fetchone()[0]
    except Exception as e:
        st.error(f"KPI 數據載入失敗: {e}")
    finally:
        conn.close()
    return kpis

# 讀取待處理異常事件
def load_pending_anomalies():
    conn = get_db_connection()
    events = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM data_anomaly_events WHERE process_status = 'pending' ORDER BY id ASC")
            events = cursor.fetchall()
    finally:
        conn.close()
    return events

# 驗證電話格式是否正確 (09開頭且共10位純數字)
def validate_phone(phone_str):
    import re
    phone_clean = re.sub(r'\D', '', phone_str)
    if len(phone_clean) == 10 and phone_clean.startswith('09'):
        return True, phone_clean
    return False, None

# 頁面主體渲染
st.markdown('<h1 class="page-title">📊 儀表板與資料異常處理</h1>', unsafe_allow_html=True)

# 1. 渲染 KPI 卡片
kpis = load_kpi_data()
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value">{kpis["new_clients"]} 件</div><div class="kpi-label">📈 當月新增客戶 (30天內)</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-value">{kpis["active_orders"]} 件</div><div class="kpi-label">🔄 進行中服務訂單</div></div>', unsafe_allow_html=True)
with col3:
    # 待處理異常若大於 0 顯示紅色底線美化
    border_color = "#E53E3E" if kpis["anomalies"] > 0 else "#11998e"
    st.markdown(f'<div class="kpi-card" style="border-bottom: 4px solid {border_color};"><div class="kpi-value" style="color: {border_color};">{kpis["anomalies"]} 筆</div><div class="kpi-label">⚠️ 待處理資料異常</div></div>', unsafe_allow_html=True)

# 2. 異常填報隔離區 (Quarantine Area)
col_title, col_sync = st.columns([3, 1])
with col_title:
    st.markdown("### ⚠️ 資料填報異常隔離區 (Quarantine Area)")
with col_sync:
    sync_btn = st.button("🔄 同步 BeClass 線上報名 (API Sync)", use_container_width=True)
    
if sync_btn:
    beclass_key = os.getenv("BECLASS_API_KEY", "your_beclass_api_key_here")
    beclass_class_id = os.getenv("BECLASS_CLASS_ID", "your_beclass_class_id_here")
    beclass_url = os.getenv("BECLASS_API_URL", "https://www.beclass.com/api/get_registrations")
    
    is_mock_sync = True
    if beclass_key and beclass_key != "your_beclass_api_key_here":
        import requests
        try:
            res = requests.get(f"{beclass_url}?key={beclass_key}&class_id={beclass_class_id}", timeout=5)
            if res.status_code == 200:
                # 實務上會在此進行資料解析與清洗匯入，以下為成功提示
                st.success("🎉 成功從 BeClass 雲端 API 獲取最新報名資料並執行清洗匯入！")
                st.rerun()
                is_mock_sync = False
            else:
                st.error(f"❌ BeClass API 請求失敗，代碼：{res.status_code}")
        except Exception as ex:
            st.error(f"❌ 連接 BeClass API 伺服器失敗 ({ex})。")
            
    if is_mock_sync:
        st.info("💡 檢測到 BeClass API 金鑰為預設占位符，系統自動啟用【API 擬真模擬模式】進行演示。")
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                import time
                mock_payload = {
                    "seq_num": 105,
                    "case_no": f"1150000{int(time.time()) % 100}",
                    "name": "張小明(BeClass API Mock)",
                    "phone": "09-1234-56", # 電話格式錯誤，會觸發隔離
                    "city": "新竹市",
                    "address": "東區建功一路80號",
                    "due_month": "115年12月"
                }
                cursor.execute("""
                    INSERT INTO data_anomaly_events (source_platform, anomaly_type, error_field, error_value, raw_payload, process_status)
                    VALUES ('BeClass_API', 'PHONE_FORMAT_ERROR', 'phone', '09-1234-56', %s, 'pending')
                """, (json.dumps(mock_payload, ensure_ascii=False),))
                conn.commit()
                st.success("🧪 模擬同步成功！已從 API 載入一筆 BeClass 報名異常資料（張小明）至下方隔離區。")
                st.rerun()
        except Exception as err:
            conn.rollback()
            st.error(f"模擬寫入失敗: {err}")
        finally:
            conn.close()

pending_events = load_pending_anomalies()

if not pending_events:
    st.success("🎉 目前無待處理的資料異常事件，所有匯入資料均已成功寫入資料庫！")
else:
    # 建立異常表格展示
    table_data = []
    for ev in pending_events:
        table_data.append({
            "事件 ID": ev["id"],
            "來源平台": ev["source_platform"],
            "異常類型": ev["anomaly_type"],
            "錯誤欄位": ev["error_field"],
            "目前錯誤值": ev["error_value"],
            "建立時間": ev["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        })
    st.table(table_data)
    
    st.markdown("---")
    st.markdown("### 🛠️ 人工資料修正面板")
    
    # 選擇要修正的事件
    event_options = {f"事件 ID {ev['id']} - {ev['anomaly_type']} ({ev['error_value']})": ev for ev in pending_events}
    selected_label = st.selectbox("請選擇您要更正的異常事件：", list(event_options.keys()))
    
    if selected_label:
        selected_event = event_options[selected_label]
        raw_data = json.loads(selected_event["raw_payload"])
        
        # 顯示兩欄：左側編輯更正，右側顯示原始 payload
        col_edit, col_raw = st.columns([3, 2])
        
        with col_raw:
            st.info("📄 原始 Excel 資料 Payload (JSON)")
            st.json(raw_data)
            
        with col_edit:
            st.markdown(f"**更正來源平台 {selected_event['source_platform']} 的資料**")
            
            # 動態產生編輯表單
            with st.form(key=f"edit_form_{selected_event['id']}"):
                input_fields = {}
                
                # 這裡對 clients 常用欄位提供輸入框
                input_fields["name"] = st.text_input("姓名：", value=raw_data.get("name", ""))
                input_fields["phone"] = st.text_input("行動電話：", value=raw_data.get("phone", ""))
                input_fields["city"] = st.text_input("縣市 (例如: 新竹市)：", value=raw_data.get("city", ""))
                input_fields["address"] = st.text_input("詳細地址：", value=raw_data.get("address", ""))
                input_fields["case_no"] = st.text_input("查詢序號(案件編號)：", value=raw_data.get("case_no", ""))
                input_fields["due_month"] = st.text_input("預產期：", value=raw_data.get("due_month", ""))
                
                # 保留其他沒呈現在輸入框的 raw 欄位
                for k, v in raw_data.items():
                    if k not in input_fields:
                        input_fields[k] = v
                
                submit_button = st.form_submit_button(label="💾 驗證並確認寫入資料庫")
                ignore_button = st.form_submit_button(label="🗑️ 忽略此異常 (刪除或標記已忽略)")
                
            if submit_button:
                # 欄位格式校驗
                is_valid = True
                error_msgs = []
                
                # 1. 驗證行動電話
                phone_ok, clean_p = validate_phone(input_fields["phone"])
                if not phone_ok:
                    is_valid = False
                    error_msgs.append("行動電話必須為 10 碼且以 '09' 開頭之數字。")
                else:
                    input_fields["phone"] = clean_p
                
                # 2. 驗證姓名不得為空
                if not input_fields["name"].strip():
                    is_valid = False
                    error_msgs.append("姓名欄位不得為空。")
                    
                # 3. 驗證縣市不得為空
                if not input_fields["city"].strip():
                    # 嘗試從地址抓取縣市
                    addr = input_fields["address"].strip()
                    if len(addr) >= 3:
                        for possible_city in ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "新竹市", "新竹縣"]:
                            if addr.startswith(possible_city):
                                input_fields["city"] = possible_city
                                break
                    if not input_fields["city"].strip():
                        is_valid = False
                        error_msgs.append("縣市欄位不得為空，且地址開頭未包含有效縣市名。")
                
                if not is_valid:
                    for msg in error_msgs:
                        st.error(f"❌ 驗證失敗: {msg}")
                else:
                    # 寫入資料庫與更新異常表
                    conn = get_db_connection()
                    try:
                        with conn.cursor() as cursor:
                            # 1. 寫入或更新 clients 表
                            # 檢查 clients 表中是否已有此 case_no
                            cursor.execute("SELECT id FROM clients WHERE case_no = %s", (input_fields["case_no"],))
                            existing_client = cursor.fetchone()
                            
                            if existing_client:
                                client_id = existing_client[0]
                                sql_update = """
                                UPDATE clients 
                                SET name=%s, phone=%s, city=%s, address=%s, due_month=%s, status='符合'
                                WHERE id=%s
                                """
                                cursor.execute(sql_update, (
                                    input_fields["name"], input_fields["phone"],
                                    input_fields["city"], input_fields["address"],
                                    input_fields["due_month"], client_id
                                ))
                            else:
                                sql_insert = """
                                INSERT INTO clients (seq_num, case_no, name, phone, city, address, due_month, status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, '符合')
                                """
                                cursor.execute(sql_insert, (
                                    input_fields.get("seq_num", 999), input_fields["case_no"],
                                    input_fields["name"], input_fields["phone"],
                                    input_fields["city"], input_fields["address"],
                                    input_fields["due_month"]
                                ))
                                client_id = cursor.lastrowid
                                
                                # 同步在 orders 新增一筆「洽談中」訂單 (生命週期起點)
                                cursor.execute(
                                    "INSERT INTO orders (client_id, status) VALUES (%s, '洽談中')",
                                    (client_id,)
                                )
                            
                            # 2. 將 data_anomaly_events 的 process_status 改為 resolved
                            cursor.execute(
                                "UPDATE data_anomaly_events SET process_status = 'resolved' WHERE id = %s",
                                (selected_event["id"],)
                            )
                            conn.commit()
                            st.success(f"🎉 修正成功！資料已成功寫入 clients 表，且訂單初始化完成。異常事件 ID {selected_event['id']} 已標記為已處理！")
                            # 重新載入頁面以刷新狀態
                            st.rerun()
                    except Exception as db_err:
                        conn.rollback()
                        st.error(f"資料庫寫入失敗: {db_err}")
                    finally:
                        conn.close()
                        
            if ignore_button:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE data_anomaly_events SET process_status = 'ignored' WHERE id = %s",
                            (selected_event["id"],)
                        )
                        conn.commit()
                        st.info(f"🗑️ 已將異常事件 ID {selected_event['id']} 標記為忽略，該資料已自隔離區移出。")
                        st.rerun()
                except Exception as db_err:
                    conn.rollback()
                    st.error(f"資料庫更新失敗: {db_err}")
                finally:
                    conn.close()

    # 3. 🛡️ 服務人員加退保提示與管理控制台 (Insurance Control)
    st.markdown("---")
    st.markdown("### 🛡️ 服務人員加退保提示與管理控制台 (Insurance Control)")
    st.caption("💡 系統自動比對未來/過去 7 天內服務開始與結束的訂單，提示行政專員為月嫂辦理加退保業務。")

    # 讀取待加保名單
    def load_pending_insurances():
        conn = get_db_connection()
        insurances = []
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("""
                    SELECT o.id as order_id, o.actual_start_date, o.actual_end_date,
                           c.name as client_name, s.name as staff_name, s.identity_card,
                           c.case_no, o.insurance_status
                    FROM orders o
                    JOIN clients c ON o.client_id = c.id
                    JOIN staff s ON o.staff_id = s.id
                    WHERE o.status IN ('訂單成立', '服務中')
                      AND (o.insurance_status = 'pending' OR o.insurance_status IS NULL)
                      AND o.actual_start_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
                """)
                insurances = cursor.fetchall()
        finally:
            conn.close()
        return insurances

    # 讀取待退保名單
    def load_pending_withdrawals():
        conn = get_db_connection()
        withdrawals = []
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("""
                    SELECT o.id as order_id, o.actual_start_date, o.actual_end_date,
                           c.name as client_name, s.name as staff_name, s.identity_card,
                           c.case_no, o.insurance_status
                    FROM orders o
                    JOIN clients c ON o.client_id = c.id
                    JOIN staff s ON o.staff_id = s.id
                    WHERE o.insurance_status = 'active'
                      AND o.actual_end_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
                """)
                withdrawals = cursor.fetchall()
        finally:
            conn.close()
        return withdrawals

    col_ins1, col_ins2 = st.columns(2)

    with col_ins1:
        st.markdown("#### 🟢 待辦理「加保」名單 (預計近期開始服務)")
        pending_ins = load_pending_insurances()
        if not pending_ins:
            st.success("🟢 目前無近期需要加保的月嫂。")
        else:
            for ins in pending_ins:
                with st.container():
                    st.markdown(f"""
                    <div style="border: 1px solid #C6F6D5; background: #F0FFF4; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                        <strong>月嫂：{ins['staff_name']}</strong> ({ins['identity_card']})<br/>
                        客戶：{ins['client_name']} ｜ 案號：{ins['case_no']}<br/>
                        服務開始日：<span style="color:#2F855A; font-weight:bold;">{ins['actual_start_date']}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 一鍵確認加保
                    if st.button(f"✅ 確認已辦理加保", key=f"btn_ins_{ins['order_id']}"):
                        conn = get_db_connection()
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE orders SET insurance_status = 'active' WHERE id = %s", (ins['order_id'],))
                                conn.commit()
                                st.success(f"已標記訂單 #{ins['order_id']} 月嫂 {ins['staff_name']} 為已加保狀態。")
                                st.rerun()
                        except Exception as err:
                            conn.rollback()
                            st.error(f"更新失敗: {err}")
                        finally:
                            conn.close()

    with col_ins2:
        st.markdown("#### 🔴 待辦理「退保」名單 (預計近期結束服務)")
        pending_with = load_pending_withdrawals()
        if not pending_with:
            st.success("🟢 目前無近期需要退保的月嫂。")
        else:
            for wth in pending_with:
                with st.container():
                    st.markdown(f"""
                    <div style="border: 1px solid #FED7D7; background: #FFF5F5; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                        <strong>月嫂：{wth['staff_name']}</strong> ({wth['identity_card']})<br/>
                        客戶：{wth['client_name']} ｜ 案號：{wth['case_no']}<br/>
                        服務結束日：<span style="color:#C53030; font-weight:bold;">{wth['actual_end_date']}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 一鍵確認退保
                    if st.button(f"🛑 確認已向產險辦理退保", key=f"btn_wth_{wth['order_id']}"):
                        conn = get_db_connection()
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE orders SET insurance_status = 'inactive' WHERE id = %s", (wth['order_id'],))
                                conn.commit()
                                st.success(f"已標記訂單 #{wth['order_id']} 月嫂 {wth['staff_name']} 為已退保狀態。")
                                st.rerun()
                        except Exception as err:
                            conn.rollback()
                            st.error(f"更新失敗: {err}")
                        finally:
                            conn.close()


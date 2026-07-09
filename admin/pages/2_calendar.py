# -*- coding: utf-8 -*-
"""
File: admin/pages/2_calendar.py
Description: 頁面二：📅 月嫂行事曆與排班 (Staff & Availability) - 出勤精算控制台版
"""
import streamlit as st
import pymysql
import os
import json
import calendar
import pandas as pd
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

st.set_page_config(
    page_title="月嫂行事曆與排班 - 月子工會系統",
    page_icon="📅",
    layout="wide"
)

# 動態設定 sys.path 確保能定位到 admin.utils
import sys
if "." not in sys.path:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# 導入共用日期算法與配置
from admin.utils import calculate_refined_attendance_dates, WEEKDAYS_MAP, WEEKDAYS_ENG, ROC_HOLIDAYS, reload_holidays, get_db_connection

# 嵌入客製化 CSS 樣式
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Microsoft JhengHei', sans-serif;
    }
    
    .page-title {
        background: linear-gradient(135deg, #FF9966 0%, #FF5E62 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
    
    /* 月曆表格基本樣式 */
    .calendar-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 15px;
        background: #FFFFFF;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border-radius: 8px;
        overflow: hidden;
    }
    
    .calendar-th {
        background-color: #F7FAFC;
        color: #4A5568;
        font-weight: 600;
        text-align: center;
        padding: 12px;
        border: 1px solid #E2E8F0;
        width: 14.28%;
    }
    
    .calendar-cell {
        height: 100px;
        vertical-align: top;
        padding: 8px;
        border: 1px solid #E2E8F0;
        position: relative;
    }
    
    .calendar-day-num {
        font-weight: bold;
        font-size: 1rem;
        color: #2D3748;
        margin-bottom: 6px;
    }
    
    .calendar-cell-empty {
        background-color: #EDF2F7;
        height: 100px;
        border: 1px solid #E2E8F0;
    }
    
    /* 狀態區標籤 */
    .cell-badge {
        font-size: 0.78rem;
        font-weight: 600;
        padding: 4px 6px;
        border-radius: 4px;
        display: block;
        margin-top: 4px;
        text-align: center;
        line-height: 1.3;
    }
    
    /* 各種狀態配色 */
    .cell-free { background-color: #E6FFFA; color: #234E52; border-left: 3px solid #319795; }
    .cell-booked { background-color: #EBF8FF; color: #2B6CB0; border-left: 3px solid #3182CE; }
    .cell-leave { background-color: #FFFDF5; color: #975A16; border-left: 3px solid #D69E2E; }
    .cell-buffer { background-color: #FFFAF0; color: #DD6B20; border-left: 3px solid #ED8936; }
    .cell-rest { background-color: #F7FAFC; color: #718096; border-left: 3px solid #A0AEC0; }
    .cell-holiday { background-color: #FFF5F5; color: #9B2C2C; border-left: 3px solid #E53E3E; }
</style>
""", unsafe_allow_html=True)

# 初始化/升級資料庫 Schema (安全添加 custom_attendance_json 與 roc_holidays 等欄位與表格)
def init_db_schema():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 升級 orders 新增 custom_attendance_json (JSON 狀態覆寫)
            try:
                cursor.execute("ALTER TABLE orders ADD COLUMN custom_attendance_json TEXT")
                conn.commit()
            except pymysql.err.OperationalError as e:
                if e.args[0] != 1060: # Column already exists
                    raise e
            # 升級 orders 新增 service_mode
            try:
                cursor.execute("ALTER TABLE orders ADD COLUMN service_mode VARCHAR(20) DEFAULT '連續服務'")
                conn.commit()
            except pymysql.err.OperationalError as e:
                if e.args[0] != 1060:
                    raise e
            # 升級 orders 新增 actual_end_date
            try:
                cursor.execute("ALTER TABLE orders ADD COLUMN actual_end_date DATE")
                conn.commit()
            except pymysql.err.OperationalError as e:
                if e.args[0] != 1060:
                    raise e
            
            # 建立 roc_holidays 資料表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS roc_holidays (
                    holiday_date DATE PRIMARY KEY COMMENT '國定假日日期',
                    holiday_name VARCHAR(100) NOT NULL COMMENT '假日名稱',
                    is_custom BOOLEAN DEFAULT FALSE COMMENT '是否為手動新增'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            conn.commit()
            
            # 如果表格為空，預載 utils 中的預設假日
            cursor.execute("SELECT COUNT(*) as cnt FROM roc_holidays;")
            count_row = cursor.fetchone()
            if count_row and count_row[0] == 0:
                insert_query = """
                    INSERT INTO roc_holidays (holiday_date, holiday_name, is_custom) 
                    VALUES (%s, %s, FALSE) 
                    ON DUPLICATE KEY UPDATE holiday_name = VALUES(holiday_name);
                """
                holiday_data = [(date_str, name) for date_str, name in ROC_HOLIDAYS.items()]
                cursor.executemany(insert_query, holiday_data)
                conn.commit()
    finally:
        conn.close()

def sync_holidays_from_db_to_mem():
    """
    將資料庫中的國定假日加載到記憶體
    """
    try:
        conn = get_db_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT holiday_date, holiday_name FROM roc_holidays;")
                rows = cursor.fetchall()
                if rows:
                    db_holidays = {row['holiday_date'].strftime("%Y-%m-%d"): row['holiday_name'] for row in rows}
                    reload_holidays(db_holidays)
        finally:
            conn.close()
    except Exception:
        pass

# 執行 Schema 升級與假日同步
try:
    init_db_schema()
    sync_holidays_from_db_to_mem()
except Exception as e:
    st.sidebar.warning(f"⚠️ 無法初始化資料庫或載入假日資料：{e}")

# 讀取在職月嫂
def load_staff_list():
    conn = get_db_connection()
    staff_list = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id, name, weekly_rest_days FROM staff WHERE status='active' ORDER BY name ASC")
            staff_list = cursor.fetchall()
    finally:
        conn.close()
    return staff_list

# 讀取特定月嫂已排日程
def load_staff_schedules(staff_id):
    conn = get_db_connection()
    bookings = []
    availabilities = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT b.*, c.name as client_name 
                FROM staff_bookings b
                LEFT JOIN clients c ON b.client_id = c.id
                WHERE b.staff_id = %s 
            """, (staff_id,))
            bookings = cursor.fetchall()
            
            cursor.execute("""
                SELECT * FROM staff_availability 
                WHERE staff_id = %s 
            """, (staff_id,))
            availabilities = cursor.fetchall()
    finally:
        conn.close()
    return bookings, availabilities

# 衝突比對核心邏輯
def check_scheduling_conflict(staff_id, start_date, end_date, exclude_order_id=None):
    conn = get_db_connection()
    conflict_type = 'NONE'
    conflict_details = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 如果是覆寫特定訂單，我們排班比對需要排除該訂單的已排日程，以防與自己衝突
            sql = """
                SELECT b.*, c.name as client_name 
                FROM staff_bookings b
                LEFT JOIN clients c ON b.client_id = c.id
                WHERE b.staff_id = %s 
                  AND b.start_date <= %s 
                  AND b.end_date >= %s
            """
            params = [staff_id, end_date, start_date]
            
            if exclude_order_id:
                # 取得該訂單的 client_id
                cursor.execute("SELECT client_id FROM orders WHERE id=%s", (exclude_order_id,))
                cid_row = cursor.fetchone()
                if cid_row:
                    sql += " AND b.client_id != %s"
                    params.append(cid_row["client_id"])
                    
            cursor.execute(sql, tuple(params))
            conflicts = cursor.fetchall()
            
            for conf in conflicts:
                if conf["client_id"] == 0:
                    conflict_type = 'HARD_BLOCK'
                    conflict_details.append(f"與已請假時段 ({conf['start_date']} ~ {conf['end_date']}) 重疊！")
                else:
                    conflict_type = 'HARD_BLOCK'
                    conflict_details.append(f"與客戶 {conf['client_name']} 的服務時段 ({conf['start_date']} ~ {conf['end_date']}) 重疊！")
    finally:
        conn.close()
    return conflict_type, conflict_details


# 頁面渲染
st.markdown('<h1 class="page-title">📅 月嫂行事曆與排班</h1>', unsafe_allow_html=True)

staff_list = load_staff_list()
if not staff_list:
    st.warning("⚠️ 目前資料庫中無在職服務人員，請先進行資料匯入！")
else:
    # 1. 選擇人員與年月切換
    col_sel_s, col_sel_y, col_sel_m = st.columns([2, 1, 1])
    with col_sel_s:
        staff_options = {s["name"]: s for s in staff_list}
        selected_name = st.selectbox("🔍 請選取要管理排班的服務人員：", list(staff_options.keys()))
        
    with col_sel_y:
        selected_year = st.selectbox("年份：", [2024, 2025, 2026, 2027, 2028, 2029, 2030], index=2) # 預設 2026
    with col_sel_m:
        selected_month = st.selectbox("月份：", list(range(1, 13)), index=datetime.today().month - 1)

    if selected_name:
        selected_staff = staff_options[selected_name]
        staff_id = selected_staff["id"]
        
        # 解析固定休假偏好
        rest_days_raw = selected_staff["weekly_rest_days"]
        rest_days = []
        if rest_days_raw:
            try:
                rest_days = json.loads(rest_days_raw) if isinstance(rest_days_raw, str) else rest_days_raw
            except Exception:
                rest_days = []
                
        rest_days_zh = [WEEKDAYS_MAP[d] for d in rest_days if d in WEEKDAYS_MAP]
        rest_days_str = "、".join(rest_days_zh) if rest_days_zh else "無固定休假"
        
        st.info(f"👤 **服務人員：{selected_name}** ｜ 🌲 **每週固定休假偏好：{rest_days_str}**")
        
        # 2. 載入並計算日程
        bookings, availabilities = load_staff_schedules(staff_id)
        
        # 3. 繪製「月曆表格子 (Month Calendar Grid View)」
        st.markdown(f"### 📅 {selected_year} 年 {selected_month} 月 檔期月曆")
        
        # 設定每週第一天為週日
        calendar.setfirstweekday(6)
        weeks = calendar.monthcalendar(selected_year, selected_month)
        
        # 繪製月曆 HTML 表格
        html_cal = """
        <table class="calendar-table">
            <thead>
                <tr>
                    <th class="calendar-th" style="color: #E53E3E;">週日</th>
                    <th class="calendar-th">週一</th>
                    <th class="calendar-th">週二</th>
                    <th class="calendar-th">週三</th>
                    <th class="calendar-th">週四</th>
                    <th class="calendar-th">週五</th>
                    <th class="calendar-th" style="color: #3182CE;">週六</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for week in weeks:
            html_cal += "<tr>"
            for d_num in week:
                if d_num == 0:
                    # 非本月日期補白
                    html_cal += '<td class="calendar-cell-empty"></td>'
                else:
                    d_date = date(selected_year, selected_month, d_num)
                    day_of_week_eng = WEEKDAYS_ENG[d_date.weekday()]
                    date_str = d_date.strftime("%Y-%m-%d")
                    
                    # 決定狀態
                    state_class = "cell-free"
                    state_label = "🟢 空檔可接案"
                    note = ""
                    
                    # (A) 比對 bookings (包含請假與實派)
                    matched_booking = None
                    for b in bookings:
                        b_start = b["start_date"] if isinstance(b["start_date"], date) else b["start_date"].date()
                        b_end = b["end_date"] if isinstance(b["end_date"], date) else b["end_date"].date()
                        if b_start <= d_date <= b_end:
                            matched_booking = b
                            break
                            
                    if matched_booking:
                        if matched_booking["client_id"] == 0:
                            state_class = "cell-leave"
                            state_label = "🟡 請假/不可工作"
                        else:
                            # 即使在合約預約期間，如果是月嫂的固定休假日，她也是不工作的！
                            if day_of_week_eng in rest_days:
                                state_class = "cell-rest"
                                state_label = "🌲 固定休假"
                                note = f"合約內週休({matched_booking['client_name']}案)"
                            elif date_str in ROC_HOLIDAYS:
                                # 若是國定假日
                                state_class = "cell-holiday"
                                state_label = f"🎏 國定休假: {ROC_HOLIDAYS[date_str]}"
                                note = f"國假({matched_booking['client_name']}案)"
                            else:
                                state_class = "cell-booked"
                                state_label = f"🔵 客戶: {matched_booking['client_name']}"
                    else:
                        # (B) 檢查是否落在已排班服務結束後的 7 天緩衝期內
                        is_buffer = False
                        buffer_client = ""
                        for b in bookings:
                            if b["client_id"] > 0:
                                b_end = b["end_date"] if isinstance(b["end_date"], date) else b["end_date"].date()
                                buf_start = b_end + timedelta(days=1)
                                buf_end = b_end + timedelta(days=7)
                                if buf_start <= d_date <= buf_end:
                                    is_buffer = True
                                    buffer_client = b["client_name"]
                                    break
                        if is_buffer:
                            state_class = "cell-buffer"
                            state_label = "🟠 預留緩衝"
                            note = f"防早產波動({buffer_client})"
                        else:
                            # (C) 檢查是否為固定休假日
                            if day_of_week_eng in rest_days:
                                state_class = "cell-rest"
                                state_label = "🌲 固定休假"
                                note = "週休偏好"
                            elif date_str in ROC_HOLIDAYS:
                                state_class = "cell-holiday"
                                state_label = f"🎏 國定休假: {ROC_HOLIDAYS[date_str]}"
                                note = "國定節日"
                    
                    # 繪製日期格子
                    html_cal += f"""
                    <td class="calendar-cell">
                        <div class="calendar-day-num">{d_num}</div>
                        <span class="cell-badge {state_class}">{state_label}</span>
                        {f'<div style="font-size: 0.72rem; color: #718096; margin-top: 3px; text-align: center;">{note}</div>' if note else ''}
                    </td>
                    """
            html_cal += "</tr>"
            
        html_cal += "</tbody></table>"
        # 將 HTML 緊湊化，移除所有換行與多餘縮進，防止被 Markdown 解析器錯誤當作 literal text / code block
        compact_html = html_cal.replace("\n", "").replace("    ", "").strip()
        try:
            st.html(compact_html)
        except Exception:
            st.markdown(compact_html, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 4. 新增排班、請假與出勤精算工具
        st.markdown("### 🛠️ 手動排班、請假與出勤精算控制台")
        tab_refine, tab_booking, tab_leave = st.tabs(["📊 服務出勤天數精算 (兩階段精算)", "💼 新增排班日程 (階段一)", "🟡 登記請假時段"])
        
        # (Tab 1) 出勤天數精算控制台
        with tab_refine:
            st.markdown("#### 📊 服務中案件 — 出勤天數精算面板")
            st.caption("💡 依據「兩階段時間區隔原則」，當案件確定實際服務開始日且變更為「訂單成立」後，在此針對國定假日、事假與週休進行天數精算與順延。")
            
            # 讀取指派給該月嫂的活動訂單
            conn = get_db_connection()
            active_orders = []
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT o.id as order_id, o.actual_start_date, o.actual_end_date, 
                               o.service_mode, o.custom_attendance_json,
                               c.id as client_id, c.name as client_name, c.service_days, c.service_time
                        FROM orders o
                        JOIN clients c ON o.client_id = c.id
                        WHERE o.staff_id = %s AND o.status IN ('訂單成立', '服務中')
                    """, (staff_id,))
                    active_orders = cursor.fetchall()
            finally:
                conn.close()
                
            if not active_orders:
                st.info("💡 該服務人員目前尚無「訂單成立」或「服務中」的案件，無法進行出勤天數精算。")
            else:
                order_opts = {f"客戶: {o['client_name']} (訂單 #{o['order_id']}, 天數: {o['service_days']}天)": o for o in active_orders}
                selected_order_label = st.selectbox("選擇要精算的案件：", list(order_opts.keys()))
                ord = order_opts[selected_order_label]
                
                # 編輯參數
                st.markdown("##### ⚙️ 調整精算參數")
                col_r1, col_r2, col_r3 = st.columns(3)
                
                with col_r1:
                    refine_start = st.date_input(
                        "實際服務開始日：", 
                        value=ord["actual_start_date"] if ord["actual_start_date"] else datetime.today().date(),
                        key=f"start_date_refine_{ord['order_id']}"
                    )
                with col_r2:
                    refine_mode = st.selectbox(
                        "服務方式：", 
                        ["連續服務", "週休 1 日", "週休 2 日"], 
                        index=["連續服務", "週休 1 日", "週休 2 日"].index(ord["service_mode"]) if ord["service_mode"] else 1,
                        key=f"mode_refine_{ord['order_id']}"
                    )
                with col_r3:
                    # 解析目前訂單已存的自訂狀態
                    saved_status = {}
                    if ord["custom_attendance_json"]:
                        try:
                            saved_status = json.loads(ord["custom_attendance_json"])
                        except Exception:
                            saved_status = {}
                            
                    st.caption(f"已儲存自訂狀態天數：{len(saved_status)}")
                
                # 預先計算預設狀態 (行政覆寫前的狀態)
                _, _, _, default_details = calculate_refined_attendance_dates(
                    refine_start, ord["service_days"], refine_mode, rest_days, {}
                )
                
                # 建立 st.data_editor 互動編輯表格
                st.markdown("##### 📅 每日出勤狀態彈性調整表")
                st.caption("行政可在此將特定日期改為「請假」或「國定假日休假」（系統將自動順延結束日），或將國定假日改為「工作」（月嫂正常出勤不順延）。")
                
                df_rows = []
                for idx, day_item in enumerate(default_details):
                    d_str = day_item["日期"]
                    is_hol = d_str in ROC_HOLIDAYS
                    hol_name = ROC_HOLIDAYS[d_str] if is_hol else ""
                    
                    # 讀取行政覆寫狀態，若無則為 "自動"
                    current_override = saved_status.get(d_str, "自動")
                    
                    df_rows.append({
                        "日期": d_str,
                        "星期": day_item["星期"],
                        "國定假日": hol_name if hol_name else "無",
                        "預設狀態": day_item["狀態"].split(" (")[0],
                        "行政調整": current_override
                    })
                    
                df_editor = pd.DataFrame(df_rows)
                
                # 顯示表格編輯器
                edited_df = st.data_editor(
                    df_editor,
                    column_config={
                        "日期": st.column_config.TextColumn("日期", disabled=True),
                        "星期": st.column_config.TextColumn("星期", disabled=True),
                        "國定假日": st.column_config.TextColumn("國定假日", disabled=True),
                        "預設狀態": st.column_config.TextColumn("系統預設解析", disabled=True),
                        "行政調整": st.column_config.SelectboxColumn(
                            "行政調整 (彈性覆寫)",
                            options=["自動", "工作", "請假", "每週週休", "國定假日休假"],
                            required=True
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    key=f"editor_refine_ui_{ord['order_id']}"
                )
                
                # 從 edited_df 中整理 custom_days_status 覆寫
                new_custom_status = {}
                for _, row in edited_df.iterrows():
                    if row["行政調整"] != "自動":
                        new_custom_status[row["日期"]] = row["行政調整"]
                        
                # 再次調用核心精算算法跑完顺延
                refined_end_date, buf_s, buf_e, refined_details = calculate_refined_attendance_dates(
                    refine_start, ord["service_days"], refine_mode, rest_days, new_custom_status
                )
                
                # 顯示精算結果
                st.markdown("##### 📈 試算與順延結果")
                col_m1, col_m2, col_m3 = st.columns(3)
                
                # 計算實際放假天數 (休假、請假、國定休假之和)
                total_rest_days = sum(1 for d in refined_details if d["是否計入工作日"] == "否")
                
                with col_m1:
                    st.metric("實際服務結束日", refined_end_date.strftime("%Y-%m-%d"))
                with col_m2:
                    st.metric("實計工作天數", f"{ord['service_days']} 天 (足額)")
                with col_m3:
                    st.metric("累計順延天數", f"{total_rest_days} 天")
                    
                st.markdown(f"- 預留波動緩衝期：**{buf_s.strftime('%Y-%m-%d')} ~ {buf_e.strftime('%Y-%m-%d')}**")
                
                # 衝突驗證
                conflict_type, conflict_msgs = check_scheduling_conflict(staff_id, refine_start, refined_end_date, exclude_order_id=ord["order_id"])
                
                allow_refine_save = True
                if conflict_type == 'HARD_BLOCK':
                    allow_refine_save = False
                    for msg in conflict_msgs:
                        st.error(f"❌ 衝突阻擋：{msg}")
                else:
                    st.success("🟢 排程無衝突，可儲存精算結果。")
                    
                save_refine = st.button("💾 儲存並確認天數精算結果", disabled=not allow_refine_save, key=f"btn_refine_save_{ord['order_id']}")
                
                if save_refine and allow_refine_save:
                    conn = get_db_connection()
                    try:
                        with conn.cursor() as cursor:
                            # 1. 更新 orders 的精算時間、服務方式與 JSON 狀態
                            cursor.execute("""
                                UPDATE orders 
                                SET actual_start_date = %s, actual_end_date = %s, 
                                    service_mode = %s, custom_attendance_json = %s
                                WHERE id = %s
                            """, (refine_start, refined_end_date, refine_mode, json.dumps(new_custom_status), ord["order_id"]))
                            
                            # 2. 清除該訂單原有的排班 bookings
                            cursor.execute("DELETE FROM staff_bookings WHERE staff_id = %s AND client_id = %s", (staff_id, ord["client_id"]))
                            
                            # 3. 逐日寫入 staff_bookings 供行事曆渲染與週報對帳
                            for day in refined_details:
                                d_date = datetime.strptime(day["日期"], "%Y-%m-%d").date()
                                if day["是否計入工作日"] == "是":
                                    # 寫入工作日
                                    cursor.execute("""
                                        INSERT INTO staff_bookings (staff_id, client_id, start_date, end_date)
                                        VALUES (%s, %s, %s, %s)
                                    """, (staff_id, ord["client_id"], d_date, d_date))
                                else:
                                    # 如果是行政調整的請假
                                    if "請假" in day["狀態"]:
                                        cursor.execute("""
                                            INSERT INTO staff_bookings (staff_id, client_id, start_date, end_date)
                                            VALUES (%s, 0, %s, %s)
                                        """, (staff_id, d_date, d_date))
                                        
                            conn.commit()
                            st.success("🎉 天數精算儲存成功！已將工作日與請假日寫入檔期日程，月曆已實時更新。")
                            st.rerun()
                    except Exception as err:
                        conn.rollback()
                        st.error(f"資料庫儲存失敗: {err}")
                    finally:
                        conn.close()

        # (Tab 2) 舊版階段一排班
        with tab_booking:
            st.markdown("#### 動態排程試算（階段一：簽訂合約預排排班）")
            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                b_start = st.date_input("合約預定開始日期：", value=datetime.today().date() + timedelta(days=10), key="b_start_booking_tab")
                b_days = st.number_input("合約服務天數 (工作日)：", min_value=1, max_value=60, value=24, key="b_days_booking_tab")
                
                # 配對階段：直接平鋪天數
                calc_end_date = b_start + timedelta(days=int(b_days) - 1)
                
                st.markdown(f"**🗓️ 試算排班日程結果：**")
                st.markdown(f"- 預定結束日期：**{calc_end_date.strftime('%Y-%m-%d')}**")
                
                # 衝突驗證
                conflict_type, conflict_msgs = check_scheduling_conflict(staff_id, b_start, calc_end_date)
                
                allow_save = True
                if conflict_type == 'HARD_BLOCK':
                    allow_save = False
                    for msg in conflict_msgs:
                        st.error(f"❌ 衝突阻擋：{msg}")
                else:
                    st.success("🟢 時間段無衝突，可進行儲存。")
                    
                # 選擇客戶
                conn = get_db_connection()
                clients = []
                try:
                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute("SELECT id, name FROM clients ORDER BY name ASC")
                        clients = cursor.fetchall()
                finally:
                    conn.close()
                    
                if clients:
                    client_opts = {c["name"]: c["id"] for c in clients}
                    selected_client_name = st.selectbox("選擇要關聯的客戶：", list(client_opts.keys()), key="client_sel_booking_tab")
                    client_id = client_opts[selected_client_name]
                else:
                    st.warning("⚠️ 系統無客戶資料。")
                    allow_save = False
                    
                save_booking = st.button("💾 驗證並確認寫入排班", disabled=not allow_save, key="btn_save_booking_tab")
                if save_booking and allow_save:
                    conn = get_db_connection()
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO staff_bookings (staff_id, client_id, start_date, end_date)
                                VALUES (%s, %s, %s, %s)
                            """, (staff_id, client_id, b_start, calc_end_date))
                            conn.commit()
                            st.success("🎉 排班寫入成功！")
                            st.rerun()
                    except Exception as err:
                        conn.rollback()
                        st.error(f"資料庫寫入失敗: {err}")
                    finally:
                        conn.close()
                        
            with col_b2:
                st.markdown("##### 📅 工作日排程預計明細 (無排除休假，階段二時再做精算)")
                # 以連續服務跑明細
                _, _, _, details = calculate_refined_attendance_dates(b_start, b_days, "連續服務", [])
                st.dataframe(pd.DataFrame(details), use_container_width=True, height=350)
                
        # (Tab 3) 舊版事假登載
        with tab_leave:
            st.markdown("#### 登載請假/不可工作時段 (將寫入 Bookings 並將 Client ID 設為 0)")
            
            l_start = st.date_input("請假開始日期：", value=datetime.today().date() + timedelta(days=5), key="l_start_leave_tab")
            l_end = st.date_input("請假結束日期：", value=datetime.today().date() + timedelta(days=7), key="l_end_leave_tab")
            
            if l_start > l_end:
                st.error("❌ 開始日期不能大於結束日期！")
                allow_leave_save = False
            else:
                l_conflict_type, l_conflict_msgs = check_scheduling_conflict(staff_id, l_start, l_end)
                allow_leave_save = True
                
                if l_conflict_type == 'HARD_BLOCK':
                    allow_leave_save = False
                    for msg in l_conflict_msgs:
                        st.error(f"❌ 衝突阻擋：{msg}")
                else:
                    st.success("🟢 該請假期間無衝突，可以登記。")
                    
            save_leave = st.button("💾 登記請假狀態", disabled=not allow_leave_save, key="btn_save_leave_tab")
            if save_leave and allow_leave_save:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO staff_bookings (staff_id, client_id, start_date, end_date)
                            VALUES (%s, 0, %s, %s)
                        """, (staff_id, l_start, l_end))
                        conn.commit()
                        st.success("🎉 請假登記成功！")
                        st.rerun()
                except Exception as err:
                    conn.rollback()
                    st.error(f"登記失敗: {err}")
                finally:
                    conn.close()

    # -------------------------------------------------------------
    # 🎏 國定假日與補假維護中心 (只由行政人員統一配置，獨立於月嫂選擇外)
    # -------------------------------------------------------------
    st.markdown("---")
    with st.expander("🎏 國定假日與補假維護中心 (API 同步 & 假日編輯器)", expanded=False):
        st.markdown("此工具用來管理整個系統的國定假日。您在此處設定的假日將即時套用到所有服務人員的排班算法中。")
        
        col_u1, col_u2 = st.columns([2, 1])
        
        with col_u2:
            st.markdown("##### 🔄 同步政府日曆 (ruyut/TaiwanCalendar API)")
            sync_year = st.selectbox("請選擇同步年份：", [2026, 2027, 2028, 2029, 2030], index=2, key="sync_year_select")
            sync_btn = st.button("🚀 開始同步此年份", use_container_width=True)
            
            if sync_btn:
                with st.spinner(f"正在從 API 下載 {sync_year} 年國定假日資料..."):
                    try:
                        import requests
                        url = f"https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{sync_year}.json"
                        response = requests.get(url, timeout=10)
                        
                        if response.status_code == 200:
                            holidays_data = response.json()
                            inserted_count = 0
                            
                            conn = get_db_connection()
                            try:
                                with conn.cursor() as cursor:
                                    for day_info in holidays_data:
                                        # 規則：isHoliday == True 且 description 不為空
                                        if day_info.get("isHoliday") and day_info.get("description"):
                                            date_str = day_info.get("date") # YYYYMMDD
                                            # 轉為 YYYY-MM-DD
                                            formatted_date = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
                                            holiday_name = day_info.get("description")
                                            
                                            cursor.execute("""
                                                INSERT INTO roc_holidays (holiday_date, holiday_name, is_custom)
                                                VALUES (%s, %s, FALSE)
                                                ON DUPLICATE KEY UPDATE holiday_name = VALUES(holiday_name);
                                            """, (formatted_date, holiday_name))
                                            inserted_count += 1
                                    conn.commit()
                                st.success(f"🎉 成功同步 {sync_year} 年假日！共寫入 {inserted_count} 天國定假日/補假。")
                                sync_holidays_from_db_to_mem()
                                st.rerun()
                            except Exception as db_err:
                                st.error(f"資料庫更新失敗：{db_err}")
                            finally:
                                conn.close()
                        elif response.status_code == 404:
                            st.warning(f"⚠️ {sync_year} 年的辦公日曆表尚未在 API 發布 (可能政府尚未公告)。請先手動新增假日。")
                        else:
                            st.error(f"❌ 同步失敗，API 返回狀態碼：{response.status_code}")
                    except Exception as req_err:
                        st.error(f"❌ 連線 API 出錯，請確認網路狀態！錯誤：{req_err}")
                        
        with col_u1:
            st.markdown("##### ➕ 手動新增國定假日/補假")
            col_add1, col_add2 = st.columns([1, 1])
            with col_add1:
                add_date = st.date_input("日期：", value=date.today(), key="add_holiday_date")
            with col_add2:
                add_name = st.text_input("假日名稱：", placeholder="例如：端午節補假", key="add_holiday_name")
                
            add_btn = st.button("➕ 確認新增", use_container_width=True)
            if add_btn:
                if not add_name.strip():
                    st.error("❌ 請輸入假日名稱！")
                else:
                    conn = get_db_connection()
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO roc_holidays (holiday_date, holiday_name, is_custom)
                                VALUES (%s, %s, TRUE)
                                ON DUPLICATE KEY UPDATE holiday_name = VALUES(holiday_name), is_custom = TRUE;
                            """, (add_date, add_name))
                            conn.commit()
                        st.success(f"🎉 成功新增：{add_date} ({add_name})")
                        sync_holidays_from_db_to_mem()
                        st.rerun()
                    except Exception as db_err:
                        st.error(f"資料庫寫入失敗：{db_err}")
                    finally:
                        conn.close()
                        
            st.markdown("##### 📋 現有國定假日清單")
            list_year = st.selectbox("篩選年份：", [2026, 2027, 2028, 2029, 2030], index=2, key="list_year_select")
            
            conn = get_db_connection()
            holidays_list = []
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT holiday_date, holiday_name, is_custom 
                        FROM roc_holidays 
                        WHERE YEAR(holiday_date) = %s 
                        ORDER BY holiday_date ASC;
                    """, (list_year,))
                    holidays_list = cursor.fetchall()
            except Exception:
                pass
            finally:
                conn.close()
                
            if holidays_list:
                df_holidays = pd.DataFrame(holidays_list)
                df_holidays.columns = ["日期", "假日名稱", "是否手動新增"]
                st.dataframe(df_holidays, use_container_width=True, height=200)
                
                # 刪除功能
                del_holiday_opts = {f"{row['holiday_date']} ({row['holiday_name']})": row['holiday_date'] for row in holidays_list}
                selected_del = st.selectbox("選擇要刪除的假日：", list(del_holiday_opts.keys()), key="del_holiday_select")
                del_btn = st.button("🗑️ 刪除選取的假日", type="primary")
                
                if del_btn:
                    conn = get_db_connection()
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute("DELETE FROM roc_holidays WHERE holiday_date = %s;", (del_holiday_opts[selected_del],))
                            conn.commit()
                        st.success(f"🗑️ 已刪除 {selected_del}")
                        sync_holidays_from_db_to_mem()
                        st.rerun()
                    except Exception as db_err:
                        st.error(f"刪除失敗：{db_err}")
                    finally:
                        conn.close()
            else:
                st.info(f"ℹ️ {list_year} 年目前在資料庫中無任何假日記錄。")

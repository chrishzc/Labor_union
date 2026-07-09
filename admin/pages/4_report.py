# -*- coding: utf-8 -*-
"""
File: admin/pages/4_report.py
Description: 頁面四：📋 所需表格與週報 (Reports) - 完全對齊訂單系統.csv 44欄位與出勤週報統計
"""
import streamlit as st
import pymysql
import os
import io
import json
import pandas as pd
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

st.set_page_config(
    page_title="所需表格與週報 - 月子工會系統",
    page_icon="📋",
    layout="wide"
)

# 動態設定 sys.path 確保能定位到 admin.utils
import sys
if "." not in sys.path:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# 導入共用假日字典與算法
from admin.utils import ROC_HOLIDAYS, reload_holidays, get_db_connection

# 嵌入客製化 CSS 樣式
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Microsoft JhengHei', sans-serif;
    }
    
    .page-title {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)


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

# 執行假日同步
sync_holidays_from_db_to_mem()

# 取得日期加月份邏輯
def add_months(sourcedate, months):
    import calendar
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

# 解析服務時數
def parse_service_hours(time_str):
    time_str = str(time_str).lower()
    if "24小時" in time_str or "24h" in time_str:
        return 24
    if "8小時" in time_str or "8h" in time_str:
        return 8
    if "4小時" in time_str or "4h" in time_str:
        return 4
    return 8 # 預設 8 小時

# 取得補助上限
def get_subsidy_limit(status_str):
    status_str = str(status_str)
    if "補助" in status_str or "社福" in status_str or "低收" in status_str:
        return 300
    if "一般" in status_str or "市民" in status_str:
        return 120
    return 0

# 載入訂單數據並依據「訂單系統.csv」的 44 欄位進行即時計算
def generate_aligned_master_report():
    conn = get_db_connection()
    raw_data = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT o.id as order_id, o.status as order_status, o.created_at as order_created_at,
                       o.actual_start_date, o.actual_end_date, o.contract_id, o.custom_attendance_json, o.service_mode,
                       c.name as client_name, c.identity_status, c.service_time, c.service_days,
                       c.due_month as client_due_month, c.case_no, c.address as client_address,
                       s.name as staff_name, s.weekly_rest_days,
                       p.deposit_received_at, p.balance_received_at, p.notes as payment_notes,
                       sba.bank_code as staff_bank_code, sba.account_no as staff_account_no,
                       swr.rest_type as staff_rest_type
                FROM orders o
                JOIN clients c ON o.client_id = c.id
                LEFT JOIN staff s ON o.staff_id = s.id
                LEFT JOIN payments p ON o.id = p.order_id
                LEFT JOIN staff_bank_accounts sba ON s.id = sba.staff_id AND sba.is_primary = 1
                LEFT JOIN staff_weekly_rest swr ON s.id = swr.staff_id
            """
            cursor.execute(sql)
            raw_data = cursor.fetchall()
    finally:
        conn.close()
        
    data_rows = []
    for idx, r in enumerate(raw_data):
        # 1. 服務天數與實際開始/結束日
        start_date = r["actual_start_date"]
        if not start_date:
            start_date = (r["order_created_at"] + timedelta(days=10)).date()
            
        service_days = r["service_days"] if r["service_days"] else 24
        
        # 結束日：若有經過出勤精算，則直接採用資料庫 actual_end_date，否則預排結束日為平鋪
        end_date = r["actual_end_date"]
        if not end_date:
            end_date = start_date + timedelta(days=service_days - 1)
            
        # 2. 服務時數與總時數
        service_hours = parse_service_hours(r["service_time"])
        total_hours = service_days * service_hours
        
        # 3. 補助時數與自費時數
        subsidy_limit = get_subsidy_limit(r["identity_status"])
        actual_subsidy_hours = min(total_hours, subsidy_limit)
        self_paid_hours = max(0, total_hours - actual_subsidy_hours)
        claim_days = self_paid_hours / service_hours
        
        # 4. 雇主單價配置 (一般/補助市民為 300, 非市民為 350)
        is_citizen = "非市民" not in str(r["identity_status"])
        employer_rate = 300.0 if is_citizen else 350.0
        
        # 5. 訂金金額 (一般/非市民有 5 天訂金，補助市民無訂金)
        is_subsidy_citizen = "補助" in str(r["identity_status"]) or "社福" in str(r["identity_status"])
        deposit_days = 0.0 if is_subsidy_citizen else 5.0
        deposit_amount = deposit_days * employer_rate * service_hours
        
        # 6. 第一期與第二期款計算
        first_phase_days = max(0.0, min(15.0, claim_days - deposit_days))
        first_phase_amount = first_phase_days * service_hours * employer_rate
        
        second_phase_days = max(0.0, claim_days - deposit_days - first_phase_days)
        second_phase_amount = second_phase_days * service_hours * employer_rate
        
        floor_fee = 0.0
        total_self_paid = deposit_amount + first_phase_amount + second_phase_amount + floor_fee
        
        # 7. 服務單價 (服務人員薪資單價)：一般市民300、補助市民350、非市民320 (來自訂單系統.csv規範)
        if "非市民" in str(r["identity_status"]):
            staff_rate = 320.0
        elif is_subsidy_citizen:
            staff_rate = 350.0
        else:
            staff_rate = 300.0
            
        other_bonus = 0.0
        staff_base_wage = (self_paid_hours * staff_rate) + other_bonus
        staff_subsidy_wage = actual_subsidy_hours * staff_rate
        staff_total_wage = staff_base_wage + staff_subsidy_wage
        
        # 8. 日期推算
        first_payment_date = start_date.strftime("%Y-%m-%d") if r["order_status"] in ["訂單成立", "服務中", "訂單完成"] else ""
        second_payment_date = ""
        if second_phase_days > 0 and first_payment_date:
            second_payment_date = (start_date + timedelta(days=15)).strftime("%Y-%m-%d")
            
        pay_next_month_15 = add_months(end_date, 1).replace(day=15).strftime("%Y-%m-%d")
        pay_next_next_month_15 = add_months(end_date, 2).replace(day=15).strftime("%Y-%m-%d")
        claim_next_month_5 = add_months(end_date, 1).replace(day=5).strftime("%Y-%m-%d")
        
        # 解析特殊休假/備註
        custom_attendance = {}
        if r["custom_attendance_json"]:
            try:
                custom_attendance = json.loads(r["custom_attendance_json"])
            except Exception:
                custom_attendance = {}
                
        rest_count = sum(1 for k, v in custom_attendance.items() if v in ["每週週休", "國定假日休假"])
        leave_count = sum(1 for k, v in custom_attendance.items() if v == "請假")
        
        special_rest_desc = f"休假{rest_count}天, 請假{leave_count}天" if custom_attendance else "無"
        
        # 對齊「訂單系統.csv」的 44 個欄位 (扣除 header，第一列為 欄位名稱 欄)
        row = {
            "欄位名稱": f"資料列 {idx + 1}",
            "備註": r["payment_notes"] if r["payment_notes"] else "",
            "主目錄": idx + 1,
            "訂單編號": f"#{r['order_id']}",
            "服務時段": r["service_time"] if r["service_time"] else "8小時/天",
            "服務開始日": start_date.strftime("%Y-%m-%d"),
            "客戶": r["client_name"],
            "天數": service_days,
            "補助資格": r["identity_status"] if r["identity_status"] else "一般市民",
            "服務時刻": r["service_time"], # 對應 CSV「服務時數」
            "服務時數": service_hours, # 計算用時數
            "時數": total_hours,
            "補助時數": actual_subsidy_hours,
            "自費時數": self_paid_hours,
            "請款總日數": claim_days,
            "樓層費用": floor_fee,
            "市府訂單號碼": r["case_no"] if r["case_no"] else "",
            "訂金日期-小艾": r["deposit_received_at"].strftime("%Y-%m-%d") if r["deposit_received_at"] else "未入帳",
            "雇主單價": employer_rate,
            "訂金天數": deposit_days,
            "訂金": deposit_amount,
            "第一期款入帳日-1": first_payment_date,
            "第一期款天數": first_phase_days,
            "第一期金額": first_phase_amount,
            "第二期款入帳日-1": second_payment_date,
            "第二期款天數": second_phase_days,
            "第二期金額": second_phase_amount,
            "雇主自費合計金額": total_self_paid,
            "訂單成立狀態": r["order_status"],
            "服務人員": r["staff_name"] if r["staff_name"] else "尚未指派",
            "服務單價": staff_rate,
            "其他加價": other_bonus,
            "服務薪資": staff_base_wage,
            "付款日-1": pay_next_month_15,
            "補助薪資": staff_subsidy_wage,
            "付款日-2": pay_next_next_month_15,
            "市府請款1": claim_next_month_5 if subsidy_limit > 0 else "免請款",
            "服務開始": start_date.strftime("%Y-%m-%d"),
            "服務結束": end_date.strftime("%Y-%m-%d"),
            "特殊休假": special_rest_desc,
            "服務人員銀行代號": r["staff_bank_code"] if r["staff_bank_code"] else "無",
            "服務人員帳號": r["staff_account_no"] if r["staff_account_no"] else "無",
            "休假方式": r["service_mode"] if r["service_mode"] else "連續服務",
            "預產期": r["client_due_month"] if r["client_due_month"] else "無",
            "服務薪資金額": staff_total_wage
        }
        data_rows.append(row)
        
    return pd.DataFrame(data_rows)

# 依據 CSV 範本前兩行進行拼接，並輸出二進位 Excel
def export_excel_with_template_header(df_data):
    csv_path = "document/資料庫、資料處理/訂單系統.csv"
    try:
        df_template = pd.read_csv(csv_path, encoding='utf-8')
    except Exception:
        df_template = pd.read_csv(csv_path, encoding='cp950')
        
    # 取出前兩行說明行 (計算公式 與 欄位代號)
    header_rows = df_template.iloc[:2].copy()
    
    # 將數據的 columns 名稱與模板保持一致
    df_data_aligned = df_data.copy()
    # 確保列的順序與 template 相同
    cols = list(df_template.columns)
    
    # 若 df_data 中有不在 cols 中的列或缺少，對齊之
    for c in cols:
        if c not in df_data_aligned.columns:
            df_data_aligned[c] = ""
            
    df_data_aligned = df_data_aligned[cols]
    
    # 拼接
    df_final = pd.concat([header_rows, df_data_aligned], ignore_index=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='訂單系統總表')
    return output.getvalue()

# 週報精細統計表 (統計各週實際工作日數、休假請假天數與國定假日)
def generate_attendance_weekly_summary(df_master):
    if df_master.empty:
        return pd.DataFrame()
        
    # 連接資料庫讀取所有訂單的自訂考勤紀錄
    conn = get_db_connection()
    orders_attendance = []
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id, custom_attendance_json, actual_start_date, actual_end_date FROM orders WHERE status IN ('訂單成立', '服務中')")
            orders_attendance = cursor.fetchall()
    finally:
        conn.close()
        
    # 將每日的狀態展開，並計算落在各 ISO 週的分佈
    daily_records = []
    for ord_item in orders_attendance:
        # 如果沒有精算過，就先平鋪展開
        start_d = ord_item["actual_start_date"]
        end_d = ord_item["actual_end_date"]
        if not start_d or not end_d:
            continue
            
        custom_json = ord_item["custom_attendance_json"]
        custom_status = {}
        if custom_json:
            try:
                custom_status = json.loads(custom_json)
            except Exception:
                custom_status = {}
                
        # 展開每一天
        curr = start_d
        while curr <= end_d:
            date_str = curr.strftime("%Y-%m-%d")
            status = custom_status.get(date_str, "自動")
            
            # 解析為工作日或放假
            is_holiday = date_str in ROC_HOLIDAYS
            hol_name = ROC_HOLIDAYS[date_str] if is_holiday else ""
            
            is_work = True
            status_desc = "工作"
            
            if status == "工作":
                is_work = True
                status_desc = "工作"
            elif status == "請假":
                is_work = False
                status_desc = "請假"
            elif status == "每週週休":
                is_work = False
                status_desc = "週休"
            elif status == "國定假日休假":
                is_work = False
                status_desc = f"國假休:{hol_name}"
            else:
                # 自動判定
                if is_holiday:
                    is_work = False
                    status_desc = f"國假休:{hol_name}"
                elif ord_item.get("service_mode") != "連續服務" and curr.weekday() in [5, 6]: # 預設週六日週休
                    is_work = False
                    status_desc = "週休"
                else:
                    is_work = True
                    status_desc = "工作"
                    
            daily_records.append({
                "日期": curr,
                "年份": curr.year,
                "週別": curr.isocalendar()[1],
                "是否工作": 1 if is_work else 0,
                "是否放假": 0 if is_work else 1,
                "是否請假": 1 if status_desc == "請假" else 0,
                "是否休假": 1 if status_desc in ["週休", "每週週休"] else 0,
                "是否國假休": 1 if "國假休" in status_desc else 0,
                "國假名稱": hol_name if "國假休" in status_desc else ""
            })
            curr += timedelta(days=1)
            
    if not daily_records:
        return pd.DataFrame()
        
    df_daily = pd.DataFrame(daily_records)
    weekly_stats = []
    
    # 按 ISO 週分組統計
    for (year, week), group in df_daily.groupby(["年份", "週別"]):
        week_start = datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()
        week_end = week_start + timedelta(days=6)
        
        # 國定假日名稱彙總
        holidays_in_week = [h for h in group["國假名稱"].unique() if h != ""]
        holiday_desc = "、".join(holidays_in_week) if holidays_in_week else "無"
        
        # 讀取該週的新登記件數 (與原本 Tab 2 彙整)
        df_master_week = df_master.copy()
        df_master_week['年份'] = df_master_week['建立日期'].apply(lambda x: x.year)
        df_master_week['週別'] = df_master_week['建立日期'].apply(lambda x: x.isocalendar()[1])
        
        master_group = df_master_week[(df_master_week['年份'] == year) & (df_master_week['週別'] == week)]
        new_registrations = len(master_group)
        
        weekly_stats.append({
            "週報區間": f"{week_start.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')}",
            "週數識別": f"{year}年第 {week} 週",
            "平台新登記件數": new_registrations,
            "實際工作總天數 (Work Days)": group["是否工作"].sum(),
            "每週固定休天數 (Rest Days)": group["是否休假"].sum(),
            "請假天數 (Leave Days)": group["是否請假"].sum(),
            "國定假日休假天數": group["是否國假休"].sum(),
            "國定假日名稱": holiday_desc,
            "國假雙倍薪天數 (短期委任無加給)": 0 # 依新規則固定為 0
        })
        
    return pd.DataFrame(weekly_stats)


# 渲染頁面
st.markdown('<h1 class="page-title">📋 所需表格與週報</h1>', unsafe_allow_html=True)

df_master = generate_aligned_master_report()

tab1, tab2 = st.tabs(["📋 訂單系統總表 (所需表格)", "📊 週報出勤統計表 (週報)"])

with tab1:
    st.markdown("### 📋 訂單系統總表")
    st.caption("💡 此總表已完全對齊 `訂單系統.csv` 中的 44 個欄位，並支援在匯出 Excel 時自動保留說明與公式行。")
    
    if df_master.empty:
        st.info("💡 目前資料庫中無任何訂單資料。")
    else:
        # 匯出 Excel
        excel_data = export_excel_with_template_header(df_master)
        st.download_button(
            label="📥 匯出並下載所需表格 Excel (.xlsx)",
            data=excel_data,
            file_name="訂單系統總表_所需表格.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.dataframe(df_master, use_container_width=True)

with tab2:
    st.markdown("### 📊 週報出勤精細統計表")
    st.caption("💡 此統計表已依照「週報精細統計規範」，精確統計各週的出勤工作天數、休假/請假天數，以及國定假日狀態。")
    
    if df_master.empty:
        st.info("💡 目前資料庫中無資料，無法生成統計。")
    else:
        df_weekly = generate_attendance_weekly_summary(df_master)
        
        if df_weekly.empty:
            st.info("💡 目前尚無進入「訂單成立」或「服務中」的排班資料，無法進行出勤精細統計。")
        else:
            # 匯出週報
            weekly_excel = io.BytesIO()
            with pd.ExcelWriter(weekly_excel, engine='openpyxl') as writer:
                df_weekly.to_excel(writer, index=False, sheet_name='週報統計')
            
            st.download_button(
                label="📥 匯出並下載週報統計 Excel (.xlsx)",
                data=weekly_excel.getvalue(),
                file_name="週報統計表.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.dataframe(df_weekly, use_container_width=True)

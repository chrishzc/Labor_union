# -*- coding: utf-8 -*-
"""
File: admin/utils.py
Description: 共用工具函數與排班日期算法
"""
from datetime import timedelta
import os
import pymysql
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

def get_db_connection():
    """統一建立資料庫連線，並自動讀取 .env 中的設定"""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "1234"),
        database=os.getenv("DB_DATABASE", "union_db"),
        charset="utf8mb4",
        connect_timeout=10
    )
WEEKDAYS_MAP = {
    "Monday": "週一",
    "Tuesday": "週二",
    "Wednesday": "週三",
    "Thursday": "週四",
    "Friday": "週五",
    "Saturday": "週六",
    "Sunday": "週日"
}
WEEKDAYS_ENG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# 中華民國 2026/2027/2028 年國定假日字典 (作為初始預設及離線 fallback 用)
ROC_HOLIDAYS = {
    # 2026 年
    "2026-01-01": "元旦",
    "2026-02-16": "除夕",
    "2026-02-17": "春節初一",
    "2026-02-18": "春節初二",
    "2026-02-19": "春節初三",
    "2026-02-20": "春節初四",
    "2026-02-21": "春節初五",
    "2026-02-23": "春節補假",
    "2026-02-28": "和平紀念日",
    "2026-03-02": "和平紀念日補假",
    "2026-04-03": "兒童節",
    "2026-04-04": "清明節",
    "2026-06-19": "端午節",
    "2026-09-25": "中秋節",
    "2026-10-10": "國慶日",
    "2026-10-12": "國慶日補假",
    # 2027 年
    "2027-01-01": "元旦",
    "2027-02-05": "除夕",
    "2027-02-06": "春節初一",
    "2027-02-07": "春節初二",
    "2027-02-08": "春節初三",
    "2027-02-09": "春節初四",
    "2027-02-10": "春節初五",
    "2027-02-11": "春節補假",
    "2027-02-12": "春節補假",
    "2027-02-28": "和平紀念日",
    "2027-03-01": "和平紀念日補假",
    "2027-04-04": "兒童節",
    "2027-04-05": "清明節",
    "2027-06-09": "端午節",
    "2027-09-15": "中秋節",
    "2027-10-10": "國慶日",
    "2027-10-11": "國慶日補假",
    # 2028 年 (預排假日，未來亦可由資料庫或 API 覆寫更新)
    "2028-01-01": "元旦",
    "2028-01-25": "除夕",
    "2028-01-26": "春節初一",
    "2028-01-27": "春節初二",
    "2028-01-28": "春節初三",
    "2028-01-29": "春節初四",
    "2028-01-30": "春節初五",
    "2028-01-31": "春節補假",
    "2028-02-01": "春節補假",
    "2028-02-28": "和平紀念日",
    "2028-04-03": "兒童節",
    "2028-04-04": "清明節",
    "2028-05-28": "端午節",
    "2028-05-29": "端午節補假",
    "2028-10-03": "中秋節",
    "2028-10-10": "國慶日"
}

def reload_holidays(custom_holidays_dict):
    """
    用外部載入（例如資料庫或 API 同步）的假日字典動態更新記憶體中的 ROC_HOLIDAYS
    """
    global ROC_HOLIDAYS
    ROC_HOLIDAYS.clear()
    ROC_HOLIDAYS.update(custom_holidays_dict)

def calculate_refined_attendance_dates(start_date, total_workdays, service_mode, rest_days_list, custom_days_status=None):
    """
    依據服務方式與放假/請假狀態，動態精算出勤結束日，每當遇到不計入工作日的日子，結束日自動順延一天。
    
    :param start_date: datetime.date 對象 (實際服務開始日)
    :param total_workdays: 整數 (N天服務工作日)
    :param service_mode: 字串 ("連續服務", "週休 1 日", "週休 2 日")
    :param rest_days_list: 列表，例如 ["Sunday"]
    :param custom_days_status: 字典 (key: "YYYY-MM-DD", value: "工作"/"請假"/"每週週休"/"國定假日休假")
    """
    if custom_days_status is None:
        custom_days_status = {}
        
    current_date = start_date
    workdays_counted = 0
    calendar_details = []
    
    # 防無窮迴圈上限
    max_days = 365
    days_checked = 0
    
    while workdays_counted < total_workdays and days_checked < max_days:
        days_checked += 1
        date_str = current_date.strftime("%Y-%m-%d")
        day_of_week_eng = WEEKDAYS_ENG[current_date.weekday()]
        
        is_holiday = date_str in ROC_HOLIDAYS
        holiday_name = ROC_HOLIDAYS[date_str] if is_holiday else ""
        
        # 預設狀態判定
        status_label = ""
        is_workday = True
        
        # 1. 檢查行政手動覆寫狀態
        override = custom_days_status.get(date_str)
        if override:
            if override == "工作":
                status_label = "💼 工作日 (手動設定)"
                is_workday = True
            elif override == "請假":
                status_label = "🟡 請假/不可工作 (行政登載)"
                is_workday = False
            elif override == "每週週休":
                status_label = "🌲 每週固定休 (行政登載)"
                is_workday = False
            elif override == "國定假日休假":
                status_label = f"🎏 國定休假: {holiday_name} (行政登載)"
                is_workday = False
        else:
            # 2. 無手動覆寫，進行自動規則解析
            if is_holiday:
                # 國定假日，月嫂自主決定，預設為放假 (順延)
                status_label = f"🎏 國定休假: {holiday_name} (預設休假)"
                is_workday = False
            elif service_mode != "連續服務" and day_of_week_eng in rest_days_list:
                status_label = "🌲 每週固定休 (固定排休)"
                is_workday = False
            else:
                status_label = "💼 服務工作日"
                is_workday = True
                
        # 寫入每日排程明細
        if is_workday:
            workdays_counted += 1
            calendar_details.append({
                "日期": date_str,
                "星期": WEEKDAYS_MAP[day_of_week_eng],
                "狀態": f"{status_label} (第 {workdays_counted} 天)",
                "是否計入工作日": "是"
            })
        else:
            calendar_details.append({
                "日期": date_str,
                "星期": WEEKDAYS_MAP[day_of_week_eng],
                "狀態": status_label,
                "是否計入工作日": "否"
            })
            
        if workdays_counted < total_workdays:
            current_date += timedelta(days=1)
            
    end_date = current_date
    buffer_start = end_date + timedelta(days=1)
    buffer_end = end_date + timedelta(days=7)
    
    return end_date, buffer_start, buffer_end, calendar_details

def calculate_contract_dates(start_date, service_days, rest_days_list):
    """
    舊版相容層，直接轉接呼叫新版精算算法
    """
    # 預設為週休 1 日或週休 2 日
    mode = "週休 2 日" if len(rest_days_list) >= 2 else "週休 1 日"
    if not rest_days_list:
        mode = "連續服務"
    return calculate_refined_attendance_dates(start_date, service_days, mode, rest_days_list)

# -*- coding: utf-8 -*-
"""
File: scripts/imports/import_client_hcm.py
Description: 解析並清洗 HCM 月子平台 -市府 Excel 工作表，將乾淨數據寫入 clients 表，並同步初始化 orders 為「洽談中」。
ponytail: 去重與更新時排除 line_user_id 欄位，自動為新案件在 orders 建立「洽談中」紀錄。
"""
import sys
import os
import re
from datetime import date, datetime, timedelta

import pymysql
import pandas as pd
from datetime import datetime, timezone
import json
from api.dependencies.anomaly_registry import get_anomaly_application
from domains.anomalies.registry import DesiredAlertState
from subsystems.anomalies.alert_workflow import ProjectAlertRequest
from domains.case_import.client_import_validation import EXCEL_TO_DB_COLUMN
from dotenv import load_dotenv

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Let file_watcher.py run this script as a subprocess with project imports available.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from domains.case_import.client_import_validation import (
    validate_hcm_row,
)
from subsystems.case_import.application import build_case_import_application
from subsystems.case_import.hcm_adapter import build_hcm_case_import_intent
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportWorkflowError,
)

# 從專案根目錄的 .env 讀取資料庫連線設定 (若 .env 不存在或缺少某欄位，則回退為原本的預設值)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# 資料庫連線配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'database': os.getenv('DB_DATABASE', 'union_db'),
    'charset': 'utf8mb4'
}

# 欄位映射關係 (與舊 import_excel.py 一致，但移除 案件狀態 映射以免覆寫 status)
CLIENTS_FIELD_MAPPING = {
    '項次': 'seq_num',
    '不符合原因': 'reject_reason',
    '查詢序號(案件編號)': 'case_no',
    '報名時間(建檔)': 'created_at',
    'IP位址': 'ip_address',
    '姓名': 'name',
    '性別': 'gender',
    '行動電話': 'phone',
    '縣市': 'city',
    '地址': 'address',
    '身分資格': 'identity_status',
    '服務時間': 'service_time',
    '預產期/預計服務開始月份': 'due_month',
    '預計服務日期': 'service_start_date',
    '其他事項': 'notes',
    '希望服務天數': 'service_days',
    '居住型態': 'residence_type',
    '生產方式': 'delivery_type',
    '服務方式': 'service_type',
    '寶寶資訊': 'baby_info',
    'LINE ID': 'line_id',
    '管理者註記事項': 'admin_notes'
}

def clean_phone(phone_val):
    if pd.isna(phone_val) or not phone_val:
        return None
    phone = str(phone_val).replace(" ", "").replace("-", "").strip()
    phone = re.sub(r'(?<!^)\D', '', phone)
    if phone.startswith("+886"):
        phone = "0" + phone[4:]
    elif phone.startswith("886"):
        phone = "0" + phone[3:]
    if len(phone) == 9 and phone.startswith("9"):
        phone = "0" + phone
    return phone

def clean_city_and_address(city_val, address_val):
    city = str(city_val).strip() if pd.notna(city_val) else ""
    address = str(address_val).strip() if pd.notna(address_val) else ""
    city = city.replace("臺", "台")
    address = address.replace("臺", "台")

    if not city and len(address) >= 3:
        for possible_city in ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"]:
            if address.startswith(possible_city):
                city = possible_city
                break

    if city in ["台北", "新北", "桃園", "台中", "台南", "高雄"]:
        city = city + "市"
    elif city in ["新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭", "花蓮", "台東", "澎湖", "金門", "連江"]:
        city = city + "縣"

    return city, address

def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name in ['seq_num', 'service_days']:
        try:
            return int(val)
        except:
            return None
    return str(val).strip()


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    roc_dt = _parse_roc_datetime(value)
    if roc_dt:
        return roc_dt.date()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()



def _parse_roc_datetime(text):
    text = str(text).strip()
    pattern = r"^\s*(\d{2,4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*$"
    match = re.match(pattern, text)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    year = int(year)
    if year < 1911:
        year += 1911

    hour = int(hour) if hour else 0
    minute = int(minute) if minute else 0
    second = int(second) if second else 0
    extra_days = 0
    if hour == 24:
        hour = 0
        extra_days = 1
    elif hour > 24:
        return None

    from datetime import datetime, timezone
    try:
        dt = datetime(
            year,
            int(month),
            int(day),
            hour,
            minute,
            second,
        )
        if extra_days:
            dt += timedelta(days=1)
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    roc_dt = _parse_roc_datetime(value)
    if roc_dt:
        return roc_dt
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        from datetime import timezone
        parsed = parsed.tz_localize(timezone.utc)
    return parsed.to_pydatetime()


def _load_holiday_dates(cursor):
    cursor.execute("SELECT holiday_date FROM holidays")
    return {
        parsed
        for row in cursor.fetchall()
        if (parsed := _parse_date(row["holiday_date"])) is not None
    }


def _calculate_service_end_date(start_date, service_days, service_type, holiday_dates):
    if start_date is None or not service_days or service_days < 1:
        return None

    rest_weekdays = {
        "週休1日": {6},
        "週休2日": {5, 6},
        "連續服務": set(),
    }.get(service_type, set())

    current_date = start_date
    completed_days = 0
    while completed_days < service_days:
        if current_date.weekday() not in rest_weekdays and current_date not in holiday_dates:
            completed_days += 1
            if completed_days == service_days:
                return current_date
        current_date += timedelta(days=1)

    return None


def _result(inserted=0, skipped_existing=0, review_required=0, failed=0):
    return {
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "review_required": review_required,
        "failed": failed,
    }


def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)

    frame = _load_hcm_frame(excel_path)
    if frame is None:
        return _result(review_required=1)

    connection = _connect_database()
    if connection is None:
        return _result(failed=1)
    try:
        return _process_import_rows(frame, connection, excel_path)
    finally:
        connection.close()


def _load_hcm_frame(excel_path):
    print(f"解析 Excel 檔案：{excel_path} ...")
    workbook = pd.ExcelFile(excel_path)
    target_sheet = next(
        (
            name
            for name in workbook.sheet_names
            if _is_hcm_sheet_name(name)
        ),
        None,
    )
    if target_sheet is None:
        print("未找到包含 'HCM' 或 '市府' 關鍵字的工作表。跳過此檔案。")
        return None
    frame = workbook.parse(target_sheet)
    print(f"找到匹配工作表：'{target_sheet}'，共有 {len(frame)} 筆資料，準備匯入...")
    return frame


def _is_hcm_sheet_name(name):
    normalized_name = name.replace(" ", "").lower()
    return "hcm" in normalized_name or "市府" in normalized_name


def _connect_database():
    try:
        connection = pymysql.connect(
            **DB_CONFIG,
            cursorclass=pymysql.cursors.DictCursor,
        )
        cursor = connection.cursor()
        cursor.execute("SET NAMES utf8mb4;")
        connection.commit()
        return connection
    except Exception as error:
        print(f"資料庫連線失敗：{error}")
        return None


# Kept cohesive because it owns the one batch-level rollback and result tally.
def _process_import_rows(frame, connection, excel_path):
    counts = _result()
    application = build_case_import_application(connection)
    cursor = connection.cursor()
    try:
        for ordinal, (_, row) in enumerate(frame.iterrows(), start=1):
            outcome = _import_row(
                row,
                ordinal,
                cursor,
                application,
                excel_path,
            )
            counts[outcome] += 1
    except Exception as error:
        connection.rollback()
        _report_import_failure(error)
        counts["failed"] = 1
        return counts
    _report_import_success(counts)
    return counts


# Kept cohesive because every row gate must resolve to one observable outcome.
def _import_row(row, ordinal, cursor, application, excel_path):
    raw_row = row.to_dict()
    record = _normalized_record(row)
    case_no = record.get("case_no")
    if not case_no:
        return "review_required"
    if application.case_exists(str(case_no)):
        return "skipped_existing"
    validation_errors = validate_hcm_row(raw_row)
    if not isinstance(record.get("created_at"), datetime):
        validation_errors["報名時間(建檔)"] = "報名時間(建檔) 格式無法轉成 datetime"
    if validation_errors:
        _sanitize_hcm_record(record, validation_errors)
    try:
        intent = _case_import_intent(cursor, record)
        correlation = CorrelationId(f"hcm-case-import:{case_no}:{ordinal}")
        preview = application.preview(intent, correlation)
        command = _apply_command(intent, preview, correlation, excel_path)
        application.apply(command)
        if validation_errors:
            _emit_hcm_validation_anomaly(case_no, ordinal, validation_errors)
        return "inserted"
    except CaseImportWorkflowError as error:
        return _workflow_error_outcome(error)
    except Exception as e:
        if not hasattr(_import_row, "exception_printed_count"):
            _import_row.exception_printed_count = 0
        if _import_row.exception_printed_count < 3:
            import traceback
            traceback.print_exc()
            print(f"[除錯] 第 {ordinal} 列發生異常: {type(e).__name__}: {e}")
            _import_row.exception_printed_count += 1
        return "review_required"


def _workflow_error_outcome(error):
    if error.error.code == "case_import_duplicate":
        return "skipped_existing"
    review_categories = {"validation", "domain_blocked", "conflict"}
    if error.error.category.value in review_categories:
        return "review_required"
    raise error


def _report_import_failure(error):
    import traceback

    traceback.print_exc()
    print(f"執行出錯已 Rollback：{error}")


def _report_import_success(counts):
    print(
        "匯入成功：新增 "
        f"{counts['inserted']} 筆，略過既有 {counts['skipped_existing']} 筆，"
        f"待確認 {counts['review_required']} 筆。"
    )


def _normalized_record(row):
    record = {
        db_column: clean_data(row[excel_column], db_column)
        for excel_column, db_column in CLIENTS_FIELD_MAPPING.items()
        if excel_column in row
    }
    if "phone" in record:
        record["phone"] = clean_phone(record["phone"])
    city, address = clean_city_and_address(
        record.get("city"),
        record.get("address"),
    )
    record["city"], record["address"] = city, address
    record["created_at"] = _parse_datetime(row.get("報名時間(建檔)"))
    record["due_month"] = _parse_date(row.get("預產期/預計服務開始月份"))
    record["service_start_date"] = _parse_date(row.get("預計服務日期"))
    
    svc_type = record.get("service_type")
    if svc_type == "周休二日":
        record["service_type"] = "週休2日"
    elif svc_type in ["休周日", "休周六"]:
        record["service_type"] = "週休1日"
        
    return record


def _case_import_intent(cursor, record):
    start_date = record.get("service_start_date")
    service_days = record.get("service_days")
    if type(start_date) is not date or not isinstance(service_days, int):
        raise ValueError("case_import_service_terms_required")
    holidays = _load_holiday_dates(cursor)
    end_date = _calculate_service_end_date(
        start_date,
        service_days,
        record.get("service_type"),
        holidays,
    )
    if end_date is None:
        raise ValueError("case_import_planned_end_date_required")
    return build_hcm_case_import_intent(record, end_date)


def _apply_command(intent, preview, correlation, source_file):
    return ApplyCaseImport(
        intent,
        ExpectedVersion(preview.import_version),
        preview.fingerprint,
        IdempotencyKey(f"case-import:{intent.case_no}"),
        ActorContext("import-client-hcm"),
        f"Import negotiated HCM case from {os.path.basename(source_file)}.",
        correlation,
    )


def _sanitize_hcm_record(record, validation_errors):
    for excel_field in validation_errors:
        db_field = EXCEL_TO_DB_COLUMN.get(excel_field)
        if not db_field:
            continue
        if db_field == "identity_status":
            record[db_field] = "一般市民"
        elif db_field == "service_time":
            record[db_field] = "9 小時 08:00 17:00"
        elif db_field == "service_type":
            record[db_field] = "連續服務"
        elif db_field == "service_days":
            record[db_field] = 1
        elif db_field in ("service_start_date", "due_month"):
            record[db_field] = datetime(2000, 1, 1).date()
        elif db_field == "created_at":
            record[db_field] = datetime(2000, 1, 1, tzinfo=timezone.utc)
        else:
            record[db_field] = None


# Keep compatibility with any external callers that use the non-prefixed name.
def sanitize_hcm_record(record, validation_errors):
    return _sanitize_hcm_record(record, validation_errors)

def _emit_hcm_validation_anomaly(case_no, ordinal, validation_errors):
    app_gen = get_anomaly_application()
    application = next(app_gen)
    try:
        request = ProjectAlertRequest(
            desired=DesiredAlertState(
                definition_code="IMPORT-004",
                source_identity=str(case_no),
                source_version=1,
                active=True,
                display_snapshot={"errors": validation_errors, "row": ordinal},
            ),
            source_event_identity=f"hcm-import-validation-{case_no}-{ordinal}",
            consumer_identity="hcm-import-script-v1",
            partition_identity="default",
            occurred_at=datetime.now(timezone.utc),
        )
        application.project(request)
    finally:
        try:
            next(app_gen)
        except StopIteration:
            pass
if __name__ == "__main__":
    # 提供預設本機路徑或接收命令列參數
    excel_arg = sys.argv[1] if len(sys.argv) > 1 else "document/資料庫、資料處理/假資料_模板.xlsx"
    process_import(excel_arg)

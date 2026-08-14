"""
File: client_import_validation.py
Description: 定義 HCM 來源欄位契約與逐列驗證規則，供匯入及唯讀演練共用。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

GENDER_VALUES = {"男", "女"}
IDENTITY_STATUS_VALUES = {"一般市民", "補助市民", "非市民"}
RESIDENCE_TYPE_VALUES = {"公寓", "透天", "大樓", "公寓大廈"}
DELIVERY_TYPE_VALUES = {"自然產", "剖腹產"}
SERVICE_TYPE_VALUES = {"連續服務", "週休1日", "週休2日", "周休二日", "休周日"}
PHONE_PATTERN = re.compile(r"^09\d{8}$")
DATE_PATTERN = re.compile(r"^\d{4}/\d{2}/\d{2}$")

HCM_REQUIRED_HEADERS = frozenset({
    "案件狀態", "查詢序號(案件編號)", "報名時間(建檔)", "姓名", "行動電話",
    "身分資格", "服務時間", "預計服務日期", "希望服務天數", "服務方式",
})

VALID_CITIES = [
    "台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市",
    "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣",
    "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣",
]

# Excel 欄位名稱 -> clients 資料表欄位名稱，驗證失敗時要把這個 DB 欄位存成 NULL。
# 案件狀態沒有對應 DB 欄位（避免覆寫 orders 狀態機），不在這份清單裡。
EXCEL_TO_DB_COLUMN = {
    "報名時間(建檔)": "created_at",
    "IP位址": "ip_address",
    "姓名": "name",
    "性別": "gender",
    "行動電話": "phone",
    "縣市": "city",
    "身分資格": "identity_status",
    "服務時間": "service_time",
    "預產期/預計服務開始月份": "due_month",
    "預計服務日期": "service_start_date",
    "希望服務天數": "service_days",
    "居住型態": "residence_type",
    "生產方式": "delivery_type",
    "服務方式": "service_type",
    "寶寶資訊": "baby_info",
}


def _is_blank(value: Any) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def _normalize_phone_digits(value: Any) -> str:
    """回復 Excel 把純數字欄位讀成 int/float 時遺失的開頭 0（例如 0912345678
    被讀成 912345678.0），邏輯對齊 import_client_hcm.py 的 clean_phone()。"""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    digits = re.sub(r"\D", "", str(value).strip())
    if digits.startswith("886") and len(digits) == 12:
        digits = "0" + digits[3:]
    if len(digits) == 9 and digits.startswith("9"):
        digits = "0" + digits
    return digits



def _is_valid_integer(value):
    try:
        return int(value) > 0
    except:
        return False

def _is_valid_service_time(value):
    text = str(value).strip()
    hours_match = re.search(r"(?P<hours>\d{1,2})\s*小時", text)
    clocks = tuple(re.finditer(r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)", text))
    return hours_match is not None and len(clocks) == 2

def _is_valid_date(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, datetime) or hasattr(value, "date"):
        return True
    text = str(value).strip()
    if not DATE_PATTERN.match(text):
        # 允許民國年或各種分隔符的日期字串 (與 _parse_roc_datetime 邏輯一致)
        pattern = r"^\s*(\d{2,4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*$"
        if re.match(pattern, text):
            return True
        return False
    try:
        datetime.strptime(text, "%Y/%m/%d")
    except ValueError:
        return False
    return True


def validate_hcm_row(row: dict[str, Any]) -> dict[str, str]:
    """檢查一列 HCM 原始 Excel 資料，回傳 {欄位名稱: 錯誤說明}；乾淨則回傳空字典。"""
    errors: dict[str, str] = {}

    case_status = row.get("案件狀態")
    if _is_blank(case_status):
        errors["案件狀態"] = "不可空值"
    elif str(case_status).strip() == "不符合" and _is_blank(row.get("不符合原因")):
        errors["不符合原因"] = "案件狀態為不符合時，不可空白"

    if _is_blank(row.get("查詢序號(案件編號)")):
        errors["查詢序號(案件編號)"] = "不可空值"

    created_at = row.get("報名時間(建檔)")
    if _is_blank(created_at):
        errors["報名時間(建檔)"] = "不可空值"
    elif not _is_valid_date(created_at):
        errors["報名時間(建檔)"] = f"日期格式無法解析：{created_at}"

    if _is_blank(row.get("IP位址")):
        errors["IP位址"] = "不可空值"

    if _is_blank(row.get("姓名")):
        errors["姓名"] = "不可空值"

    gender = row.get("性別")
    if _is_blank(gender):
        errors["性別"] = "不可空值"
    elif str(gender).strip() not in GENDER_VALUES:
        errors["性別"] = f"值不在允許範圍內（男,女）：{gender}"

    phone = row.get("行動電話")
    if _is_blank(phone):
        errors["行動電話"] = "不可空值，需為09開頭的10碼字串"
    else:
        phone_digits = _normalize_phone_digits(phone)
        if not PHONE_PATTERN.match(phone_digits):
            errors["行動電話"] = f"需要09開頭的10碼字串：{phone}"

    city = row.get("縣市")
    if not _is_blank(city) and str(city).strip() not in VALID_CITIES:
        errors["縣市"] = f"不在縣市清單中：{city}"

    identity_status = row.get("身分資格")
    if _is_blank(identity_status):
        errors["身分資格"] = "不可空值"
    elif str(identity_status).strip() not in IDENTITY_STATUS_VALUES:
        errors["身分資格"] = (
            f"值不在允許範圍內（低收入戶,一般市民,非市民,中低收入戶）：{identity_status}"
        )

    service_time = row.get("服務時間")
    if _is_blank(service_time):
        errors["服務時間"] = "不可空值"
    elif not _is_valid_service_time(service_time):
        errors["服務時間"] = f"服務時間格式無法解析：{service_time}"

    due_month = row.get("預產期/預計服務開始月份")
    if _is_blank(due_month):
        errors["預產期/預計服務開始月份"] = "不可空值"
    elif not _is_valid_date(due_month):
        errors["預產期/預計服務開始月份"] = f"日期格式需為YYYY/MM/DD：{due_month}"

    start_date = row.get("預計服務日期")
    if _is_blank(start_date):
        errors["預計服務日期"] = "不可空值"
    elif not _is_valid_date(start_date):
        errors["預計服務日期"] = f"日期格式需為YYYY/MM/DD：{start_date}"

    service_days = row.get("希望服務天數")
    if _is_blank(service_days):
        errors["希望服務天數"] = "不可空值"
    elif not _is_valid_integer(service_days):
        errors["希望服務天數"] = f"必須為正整數：{service_days}"

    residence_type = row.get("居住型態")
    if _is_blank(residence_type):
        errors["居住型態"] = "不可空值"
    elif str(residence_type).strip() not in RESIDENCE_TYPE_VALUES:
        errors["居住型態"] = f"值不在允許範圍內（公寓,透天,大樓）：{residence_type}"

    delivery_type = row.get("生產方式")
    if _is_blank(delivery_type):
        errors["生產方式"] = "不可空值"
    elif str(delivery_type).strip() not in DELIVERY_TYPE_VALUES:
        errors["生產方式"] = f"值不在允許範圍內（自然產,剖腹產）：{delivery_type}"

    service_type = row.get("服務方式")
    if _is_blank(service_type):
        errors["服務方式"] = "不可空值"
    elif str(service_type).strip() not in SERVICE_TYPE_VALUES:
        errors["服務方式"] = (
            f"值不在允許範圍內（連續服務,週休1日,週休2日）：{service_type}"
        )

    if _is_blank(row.get("寶寶資訊")):
        errors["寶寶資訊"] = "不可空值"

    return errors


def fallback_case_key(name: Any, phone: Any) -> str:
    """查無案號時的替代識別鍵：error_姓名_行動電話（兩者皆空時退回用時間戳避免碰撞）。"""
    name_part = str(name).strip() if not _is_blank(name) else ""
    phone_part = _normalize_phone_digits(phone) if not _is_blank(phone) else ""
    if not name_part and not phone_part:
        return f"error_row_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    return f"error_{name_part}_{phone_part}"


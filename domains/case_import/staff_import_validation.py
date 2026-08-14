"""
File: staff_import_validation.py
Description: 定義 Staff BeClass 核心、替代欄位組與逐列驗證規則。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

from domains.case_import.client_import_validation import (
    VALID_CITIES,
    _is_blank,
    _normalize_phone_digits,
    fallback_case_key,
)

IDENTITY_CARD_PATTERN = re.compile(r"^[A-Za-z]\d{9}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BANK_BRANCH_PATTERN = re.compile(r"^\d{7}$")

STAFF_BECLASS_REQUIRED_HEADERS = frozenset({
    "查詢序號", "報名時間", "IP位址", "姓名", "銀行帳號", "銀行代3碼+分行代號4碼",
    "身分證字號", "行動電話", "EMAIL", "出生年", "月", "日", "民國出生年月日",
})
STAFF_BECLASS_CORE_HEADERS = STAFF_BECLASS_REQUIRED_HEADERS - {
    "銀行代3碼+分行代號4碼", "出生年", "月", "日", "民國出生年月日",
}
STAFF_BECLASS_BANK_BRANCH_HEADERS = frozenset({
    "銀行代3碼+分行代號4碼",
    "銀行代碼3碼+分行代號4碼",
    "銀行代號+分行代號",
})
STAFF_BECLASS_SPLIT_BIRTHDAY_HEADERS = frozenset({"出生年", "月", "日"})

VALID_CITIES_BOTH = set(VALID_CITIES) | {c.replace("台", "臺") for c in VALID_CITIES}


def matches_staff_beclass_headers(headers: set[str]) -> bool:
    """接受歷史來源已裁決的生日與銀行欄名替代形狀。"""
    if not STAFF_BECLASS_CORE_HEADERS <= headers:
        return False
    if not STAFF_BECLASS_BANK_BRANCH_HEADERS & headers:
        return False
    return (
        "民國出生年月日" in headers
        or STAFF_BECLASS_SPLIT_BIRTHDAY_HEADERS <= headers
    )


def staff_bank_branch_value(row: dict[str, Any]) -> Any:
    """依已知歷史欄名取得銀行與分行合併值。"""
    for header in STAFF_BECLASS_BANK_BRANCH_HEADERS:
        value = row.get(header)
        if not _is_blank(value):
            return value
    return None

# Excel 欄位名稱 -> staff 資料表欄位名稱，驗證失敗時要把這個 DB 欄位存成 NULL。
# 姓名不在這份清單裡：staff.name 是 NOT NULL，缺姓名時整列直接不寫入，不是存 NULL。
# 銀行代碼/帳號也不在這份清單裡：那兩欄寫在 staff_bank_accounts，不是 staff 表本身的欄位。
EXCEL_TO_DB_COLUMN = {
    "IP位址": "ip_address",
    "報名時間": "registered_at",
    "民國出生年月日": "birthday",
    "行動電話": "phone",
    "EMAIL": "email",
    "縣市": "city",
}


def _has_resolvable_birthday(row: dict[str, Any]) -> bool:
    """比照 import_staff_beclass.py 的生日解析順序：先看合併欄位，再看拆開的年/月/日。"""
    combined = row.get("民國出生年月日")
    if not _is_blank(combined):
        return True
    year, month, day = row.get("出生年"), row.get("月"), row.get("日")
    if _is_blank(year) or _is_blank(month) or _is_blank(day):
        return False
    try:
        y, m, d = int(year), int(month), int(day)
        if y < 1900:
            y += 1911
        date(y, m, d)
        return True
    except (ValueError, TypeError):
        return False


def validate_staff_row(row: dict[str, Any]) -> dict[str, str]:
    """檢查一列服務人員原始 Excel 資料，回傳 {欄位名稱: 錯誤說明}；乾淨則回傳空字典。"""
    errors: dict[str, str] = {}

    if _is_blank(row.get("姓名")):
        errors["姓名"] = "不可空值"

    identity_card = row.get("身分證字號")
    if _is_blank(identity_card):
        errors["身分證字號"] = "不可空值"
    elif not IDENTITY_CARD_PATTERN.match(str(identity_card).strip()):
        errors["身分證字號"] = f"格式需為1碼英文字母+9碼數字：{identity_card}"

    if _is_blank(row.get("報名時間")):
        errors["報名時間"] = "不可空值"

    if not _has_resolvable_birthday(row):
        errors["民國出生年月日"] = "不可空值，且需能解析成合法日期"

    phone = row.get("行動電話")
    if _is_blank(phone):
        errors["行動電話"] = "不可空值，需為09開頭的10碼字串"
    else:
        phone_digits = _normalize_phone_digits(phone)
        if not re.match(r"^09\d{8}$", phone_digits):
            errors["行動電話"] = f"需要09開頭的10碼字串：{phone}"

    email = row.get("EMAIL")
    if not _is_blank(email) and not EMAIL_PATTERN.match(str(email).strip()):
        errors["EMAIL"] = f"格式不正確：{email}"

    city = row.get("縣市")
    if not _is_blank(city) and str(city).strip() not in VALID_CITIES_BOTH:
        errors["縣市"] = f"不在縣市清單中：{city}"

    bank_account = row.get("銀行帳號")
    if not _is_blank(bank_account):
        bank_branch = staff_bank_branch_value(row)
        if not _is_blank(bank_branch):
            digits = re.sub(r"\D", "", str(bank_branch))
            if not BANK_BRANCH_PATTERN.match(digits):
                errors["銀行代3碼+分行代號4碼"] = f"值需為7碼數字（3碼銀行代碼+4碼分行代號）：{bank_branch}"

    return errors


__all__ = [
    "EXCEL_TO_DB_COLUMN",
    "STAFF_BECLASS_REQUIRED_HEADERS",
    "fallback_case_key",
    "matches_staff_beclass_headers",
    "staff_bank_branch_value",
    "validate_staff_row",
]

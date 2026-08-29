# -*- coding: utf-8 -*-
"""
File: import_staff_beclass.py
Description: 依 Staff BeClass 欄位契約唯讀演練；正式歷史採納只經 typed Application。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _resolve_project_root() -> Path:
    return Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


PROJECT_ROOT = _resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
cwd_str = os.getcwd()
if cwd_str not in sys.path:
    sys.path.insert(0, cwd_str)

from domains.case_import.staff_import_validation import (
    matches_staff_beclass_headers,
    staff_bank_branch_value,
)
from subsystems.case_import.beclass_review_intake import fingerprint_workbook
from shared_kernel.fingerprints import fingerprint_payload
from infrastructure.mysql.staff_historical_workbook_repository import (
    MySqlStaffHistoricalWorkbookRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.staff_historical_workbook_adoption import (
    StaffHistoricalWorkbookConflict,
    StaffHistoricalWorkbookService,
)

load_dotenv(str(PROJECT_ROOT / ".env"))

# No fallback target or credential is allowed for an operator entrypoint.
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "").strip(),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "").strip(),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_DATABASE", "").strip(),
    "charset": "utf8mb4",
}


def clean_phone(phone_val):
    if pd.isna(phone_val) or not phone_val:
        return None
    phone = str(phone_val).replace(" ", "").replace("-", "").strip()
    phone = re.sub(r"(?<!^)\D", "", phone)
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
    city = city.replace("台", "臺")
    address = address.replace("台", "臺")
    if not city and len(address) >= 3:
        for pc in (
            "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市", "基隆市",
            "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣",
            "嘉義縣", "屏東縣", "花蓮縣", "宜蘭縣", "臺東縣",
        ):
            if address.startswith(pc):
                city = pc
                break
    if city in ("臺北", "新北", "桃園", "臺中", "臺南", "高雄"):
        city += "市"
    elif city in ("新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "花蓮", "宜蘭", "臺東", "基隆"):
        city += "縣"
    return city, address


def clean_birth_date(year_val, month_val, day_val):
    if pd.isna(year_val) or pd.isna(month_val) or pd.isna(day_val):
        return None
    try:
        import datetime as dt

        year = int(year_val)
        if year < 1900:
            year += 1911
        return dt.date(year, int(month_val), int(day_val)).strftime("%Y-%m-%d")
    except Exception:
        return None


def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name == "seq_num":
        try:
            return int(val)
        except Exception:
            return None
    return str(val).strip()


def _result(
    inserted=0,
    adopted_existing=0,
    exact_replay=0,
    blocked_identity=0,
    identity_conflict=0,
    review_required=0,
    failed=0,
):
    return {
        "inserted": inserted,
        "adopted_existing": adopted_existing,
        "exact_replay": exact_replay,
        "blocked_identity": blocked_identity,
        "identity_conflict": identity_conflict,
        "review_required": review_required,
        "failed": failed,
    }


def _privacy_safe_staff_review_payload(record):
    return {
        "source_field_count": len(record),
        "has_identity_card": bool(str(record.get("identity_card") or "").strip()),
        "has_name": bool(str(record.get("name") or "").strip()),
        "has_phone": bool(str(record.get("phone") or "").strip()),
        "has_address": bool(str(record.get("address") or "").strip()),
    }


def _typed_historical_import(excel_path: str, source_revision: str | None):
    connection = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        service = StaffHistoricalWorkbookService(
            connection,
            MySqlStaffHistoricalWorkbookRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        preview = service.preview(excel_path, source_revision)
        digest = _staff_source_content_digest(excel_path, source_revision)
        receipt = service.apply(
            excel_path,
            source_revision,
            preview.preview_fingerprint,
            f"staff-beclass-historical:{digest}",
            "restricted-historical-staff-beclass",
            f"staff-beclass-historical:{digest}",
        )
        return _result(
            inserted=receipt.created_count,
            adopted_existing=receipt.adopted_existing_count,
            exact_replay=receipt.exact_replay_count,
            blocked_identity=receipt.blocked_identity_count,
            identity_conflict=receipt.identity_conflict_count,
            review_required=receipt.review_required_count,
        )
    except StaffHistoricalWorkbookConflict:
        return _result(review_required=1)
    except Exception:
        return _result(failed=1)
    finally:
        connection.close()


def _historical_bank_accounts(row, errors):
    account = clean_data(row.get("銀行帳號"), "account_no")
    if not account or "銀行代3碼+分行代號4碼" in errors:
        return ()
    branch = clean_data(staff_bank_branch_value(row), "bank_branch")
    bank_code = branch[:3] if branch and len(branch) >= 3 else None
    branch_code = branch[3:] if branch and len(branch) > 3 else None
    accounts = [(bank_code, branch_code, account, True)]
    additional = row.get("若有其它同銀行帳號，請一併提供。(永豐或台新)")
    if pd.notna(additional):
        digits = re.sub(r"\D", "", str(additional))
        if len(digits) >= 8:
            accounts.append((None, None, digits, False))
    return tuple(accounts)


def _historical_relations(row):
    specs = (
        ("staff_regions", ("北區", "東區", "香山區", "新竹縣", "苗栗縣"), "[其它].1"),
        ("staff_time_slots", ("4小時(上午8:30-12:30)", "4小時(下午13:00-17:00)", "8小時", "24小時"), "[其它].2"),
        ("staff_cooking_skills", ("葷食", "素食"), "[其它]"),
        ("staff_transportation", ("機車", "轎車"), None),
        ("staff_holiday_availability", ("年節農曆過年初一", "年節農曆過年初二", "年節農曆過年初三", "端午節", "中秋節", "國定假日必休"), "[其它].5"),
        ("staff_weekly_rest", ("連續服務", "週休1日", "週休2日"), "[其它].3"),
        ("staff_baby_types", ("單胞胎", "雙胞胎"), "[其它].4"),
    )
    relations = {}
    for table_name, options, other_column in specs:
        values = [(option, None) for option in options if row.get(option) == "Y"]
        if other_column:
            other = row.get(other_column)
            if pd.notna(other) and str(other).strip():
                values.append(("其他", str(other).strip()))
        relations[table_name] = (
            tuple(value[0] for value in values)
            if table_name == "staff_transportation"
            else tuple(values)
        )
    return relations


def process_import(excel_path, source_revision: str | None = None):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)
    return _typed_historical_import(excel_path, source_revision)


def _staff_source_content_digest(excel_path: str, source_revision: str | None) -> str:
    workbook_digest = fingerprint_workbook(excel_path)
    if source_revision is None:
        return workbook_digest
    normalized_revision = _normalize_source_revision(source_revision)
    return fingerprint_payload(
        {"workbook_digest": workbook_digest, "source_revision": normalized_revision}
    ).value


def _normalize_source_revision(source_revision: str) -> str:
    normalized_revision = str(source_revision).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", normalized_revision):
        raise ValueError("staff_historical_source_revision_invalid")
    return normalized_revision


def _parse_historical_staff_arguments(arguments: list[str]):
    parser = argparse.ArgumentParser(description="Staff BeClass 歷史資料唯讀演練")
    parser.add_argument("--historical-apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-revision")
    parser.add_argument("workbook")
    return parser.parse_args(arguments)


def _load_staff_beclass_frame(excel_path):
    print(f"解析 Excel 檔案：{excel_path} ...")
    with pd.ExcelFile(excel_path) as workbook:
        candidates = _staff_beclass_sheet_candidates(workbook)
    if len(candidates) != 1:
        reason = "沒有" if not candidates else "有多個"
        print(f"{reason}工作表符合 Staff BeClass 必要欄位契約，無法安全匯入。")
        return None
    return candidates[0]


def _staff_beclass_sheet_candidates(workbook):
    candidates = []
    for sheet_name in workbook.sheet_names:
        frame = workbook.parse(sheet_name=sheet_name, dtype=object)
        headers = {str(column).strip() for column in frame.columns}
        if not frame.dropna(how="all").empty and matches_staff_beclass_headers(headers):
            candidates.append((sheet_name, frame))
    return candidates


if __name__ == "__main__":
    try:
        parsed = _parse_historical_staff_arguments(sys.argv[1:])
        if parsed.historical_apply:
            from scripts.imports.historical_import_guard import authorize_historical_apply

            authorize_historical_apply(
                ["--historical-apply", parsed.workbook],
                str(DB_CONFIG["database"]),
            )
            raise RuntimeError("staff_beclass_cli_apply_guard_contract_incomplete")
        from scripts.imports.rehearse_case_import_workbook import rehearse_workbook

        receipt = rehearse_workbook("staff-beclass", Path(parsed.workbook))
        import json

        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    except RuntimeError as error:
        print(f"歷史匯入已阻擋：{error}")
        raise SystemExit(2) from error

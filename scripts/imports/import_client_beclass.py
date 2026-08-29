# -*- coding: utf-8 -*-
"""
File: import_client_beclass.py
Description: 依 Client BeClass 欄位契約選取工作表，驗證並匯入歷史報名資料。
"""
import argparse
import sys
import os
import re
import json
from pathlib import Path
import pymysql
import pandas as pd
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
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

try:
    from domains.case_import.client_beclass_validation import (
        CLIENT_BECLASS_REQUIRED_HEADERS,
        validate_client_beclass_row,
    )
except ModuleNotFoundError as e:
    print(f"\n[診斷資訊] 無法載入 domains 模組。")
    print(f"1. 計算出的專案根目錄 (PROJECT_ROOT): {PROJECT_ROOT}")
    print(f"2. 該目錄是否存在: {os.path.exists(PROJECT_ROOT)}")
    try:
        dirs = [d for d in os.listdir(PROJECT_ROOT) if os.path.isdir(os.path.join(PROJECT_ROOT, d))]
        print(f"3. 該目錄下的資料夾有: {', '.join(dirs)}")
    except Exception as ex:
        print(f"3. 無法列出該目錄內容: {ex}")
    raise e

from subsystems.case_import.beclass_review_intake import fingerprint_workbook
from infrastructure.mysql.hcm_beclass_reconciliation_adapter import (
    MySqlHcmBeClassReconciliationAdapter,
)
from infrastructure.mysql.client_beclass_workbook_import_repository import (
    ClientBeClassWorkbookImportRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.client_beclass_workbook_import import (
    ClientBeClassWorkbookConflict,
    ClientBeClassWorkbookImportService,
)

# 從專案根目錄的 .env 讀取資料庫連線設定；缺欄位時保持空值並由受控入口 fail closed。
load_dotenv(str(PROJECT_ROOT / ".env"))

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '').strip(),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', '').strip(),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_DATABASE', '').strip(),
    'charset': 'utf8mb4'
}

# BeClass \u6838\u5fc3\u6b04\u4f4d\u5c0d\u7167 (\u5176\u9918\u554f\u5377\u6b04\u4f4d\u6253\u5305\u9032 survey_details JSON)
BECLASS_CORE_MAPPING = {
    '\u9805\u6b21': 'seq_num',
    '\u67e5\u8a62\u5e8f\u865f': 'query_no',
    '\u5831\u540d\u6642\u9593': 'created_at',
    '\u59d3\u540d': 'name',
    'Email': 'email',
    '\u884c\u52d5\u96fb\u8a71': 'phone',
    '\u5e02\u8a71': 'tel',
    '\u5206\u6a5f': 'ext',
    '\u7e23\u5e02': 'city',
    '\u90f5\u905e\u5340\u865f': 'zip_code',
    '\u5730\u5740': 'address',
    '補助款退款:銀行代號+分行代號': 'refund_bank_code',
    '銀行帳號': 'refund_account_no',
    '\u7ba1\u7406\u8005\u8a3b\u8a18\u4e8b\u9805': 'admin_notes'
}

# \u904e\u6ffe\u6389\u7684\u751f\u65e5\u539f\u59cb\u6b04\u4f4d (\u5df2\u5408\u4f75\u5230 birth_date)
BIRTH_RAW_COLS = ['\u51fa\u751f\u5e74', '\u6708', '\u65e5']

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
    city = city.replace("\u81fa", "\u53f0")
    address = address.replace("\u81fa", "\u53f0")
    if not city and len(address) >= 3:
        for pc in ["\u53f0\u5317\u5e02", "\u65b0\u5317\u5e02", "\u6843\u5712\u5e02", "\u53f0\u4e2d\u5e02", "\u53f0\u5357\u5e02", "\u9ad8\u96c4\u5e02", "\u57fa\u9686\u5e02", "\u65b0\u7af9\u5e02", "\u5609\u7fa9\u5e02",
               "\u65b0\u7af9\u7e23", "\u82d7\u6817\u7e23", "\u5f70\u5316\u7e23", "\u5357\u6295\u7e23", "\u96f2\u6797\u7e23", "\u5609\u7fa9\u7e23", "\u5c4f\u6771\u7e23", "\u5b9c\u862d\u7e23", "\u82b1\u84ee\u7e23", "\u53f0\u6771\u7e23", "\u6f8e\u6e56\u7e23"]:
            if address.startswith(pc):
                city = pc
                break
    if city in ["\u53f0\u5317", "\u65b0\u5317", "\u6843\u5712", "\u53f0\u4e2d", "\u53f0\u5357", "\u9ad8\u96c4"]:
        city = city + "\u5e02"
    elif city in ["\u65b0\u7af9", "\u82d7\u6817", "\u5f70\u5316", "\u5357\u6295", "\u96f2\u6797", "\u5609\u7fa9", "\u5c4f\u6771", "\u5b9c\u862d", "\u82b1\u84ee", "\u53f0\u6771", "\u6f8e\u6e56"]:
        city = city + "\u7e23"
    return city, address

def clean_birth_date(year_val, month_val, day_val):
    if pd.isna(year_val) or pd.isna(month_val) or pd.isna(day_val):
        return None
    try:
        import datetime
        y = int(year_val)
        m = int(month_val)
        d = int(day_val)
        if y < 1900:
            y += 1911  # \u6c11\u570b\u5e74\u8f49\u897f\u5143\u5e74
        return datetime.date(y, m, d).strftime("%Y-%m-%d")
    except Exception:
        return None

def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name in ['seq_num']:
        try:
            return int(val)
        except Exception:
            return None
    return str(val).strip()


def _result(inserted=0, skipped_existing=0, review_required=0, failed=0):
    return {
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "review_required": review_required,
        "failed": failed,
    }


def _typed_historical_import(excel_path):
    connection = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        service = ClientBeClassWorkbookImportService(
            ClientBeClassWorkbookImportRepository(connection),
            MySqlHcmBeClassReconciliationAdapter(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        preview = service.preview(excel_path)
        digest = fingerprint_workbook(excel_path)
        receipt = service.apply(
            excel_path,
            f"client-beclass-historical:{digest}",
            preview.preview_fingerprint,
            "restricted-historical-client-beclass",
            f"client-beclass-historical:{digest}",
        )
        return _result(
            inserted=receipt.created_count,
            skipped_existing=receipt.exact_replay_count + receipt.existing_source_count,
            review_required=receipt.review_required_count + receipt.existing_conflict_count,
        )
    except ClientBeClassWorkbookConflict:
        return _result(review_required=1)
    except Exception:
        return _result(failed=1)
    finally:
        connection.close()


def _privacy_safe_client_review_payload(record):
    return {
        "source_field_count": len(record),
        "has_query_no": bool(str(record.get("query_no") or "").strip()),
        "has_name": bool(str(record.get("name") or "").strip()),
        "has_phone": bool(str(record.get("phone") or "").strip()),
        "has_address": bool(str(record.get("address") or "").strip()),
    }


def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)
    return _typed_historical_import(excel_path)


def _load_client_beclass_frame(excel_path):
    print(f"解析 Excel 檔案：{excel_path} ...")
    with pd.ExcelFile(excel_path) as workbook:
        candidates = _client_beclass_sheet_candidates(workbook)
    if len(candidates) != 1:
        reason = "沒有" if not candidates else "有多個"
        print(f"{reason}工作表符合 Client BeClass 必要欄位契約，無法安全匯入。")
        return None
    return candidates[0]


def _client_beclass_sheet_candidates(workbook):
    candidates = []
    for sheet_name in workbook.sheet_names:
        frame = workbook.parse(sheet_name=sheet_name, dtype=object)
        headers = {str(column).strip() for column in frame.columns}
        if not frame.dropna(how="all").empty and CLIENT_BECLASS_REQUIRED_HEADERS <= headers:
            candidates.append((sheet_name, frame))
    return candidates

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Client BeClass 歷史資料受控匯入")
        parser.add_argument("--historical-apply", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("workbook")
        parsed = parser.parse_args(sys.argv[1:])
        from scripts.imports.historical_import_guard import authorize_historical_apply

        if parsed.historical_apply:
            authorize_historical_apply(
                ["--historical-apply", parsed.workbook],
                str(DB_CONFIG["database"]),
            )
            raise RuntimeError("client_beclass_cli_apply_guard_contract_incomplete")
        from scripts.imports.rehearse_case_import_workbook import rehearse_workbook

        receipt = rehearse_workbook("client-beclass", Path(parsed.workbook))
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    except RuntimeError as error:
        print(f"歷史匯入已阻擋：{error}")
        raise SystemExit(2) from error

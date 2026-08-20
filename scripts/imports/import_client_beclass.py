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

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.beclass_review_intake import (
    fingerprint_workbook,
    masked_review_identifier,
    record_invalid_beclass_row,
)
from subsystems.case_import.hcm_beclass_reconciliation import (
    reconcile_hcm_beclass_cooking,
)
from infrastructure.mysql.client_beclass_workbook_import_repository import (
    ClientBeClassWorkbookImportRepository,
)
from subsystems.case_import.client_beclass_workbook_import import (
    ClientBeClassWorkbookConflict,
    ClientBeClassWorkbookImportService,
)

# 從專案根目錄的 .env 讀取資料庫連線設定 (若 .env 不存在或缺少某欄位，則回退為原本的預設值)
load_dotenv(str(PROJECT_ROOT / ".env"))

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'database': os.getenv('DB_DATABASE', 'union_db'),
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
            ClientBeClassWorkbookImportRepository(connection)
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


def _legacy_process_import_not_used(excel_path):
    if not os.path.exists(excel_path):
        print(f"\u932f\u8aa4\uff1a\u627e\u4e0d\u5230 Excel \u6a94\u6848\uff1a{excel_path}")
        return _result(review_required=1)

    selected = _load_client_beclass_frame(excel_path)
    if selected is None:
        return _result(review_required=1)
    target_sheet, df = selected

    source_content_digest = fingerprint_workbook(excel_path)
    print(f"已依欄位契約選取工作表，共有 {len(df)} 筆資料，準備匯入...")

    try:
        conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()
        cursor.execute("SET NAMES utf8mb4;")
        conn.commit()
    except Exception as e:
        print(f"\u8cc7\u6599\u5eab\u9023\u7dda\u5931\u6557\uff1a{e}")
        return _result(failed=1)

    inserted = 0
    skipped_existing = 0
    review_required = 0

    try:
        for source_row, (_, row) in enumerate(df.iterrows(), start=2):
            raw_row = row.to_dict()
            errors = validate_client_beclass_row(raw_row)
            phone_for_alert = raw_row.get('\u884c\u52d5\u96fb\u8a71')

            record = {}
            details = {}

            for excel_col in df.columns:
                if excel_col in BECLASS_CORE_MAPPING:
                    db_col = BECLASS_CORE_MAPPING[excel_col]
                    record[db_col] = clean_data(row[excel_col], db_col)
                elif excel_col not in BIRTH_RAW_COLS and not str(excel_col).startswith('Unnamed'):
                    # \u5176\u9918 60+ \u500b\u554f\u5377\u9078\u9805\u6253\u5305\u9032 details JSON
                    val = row[excel_col]
                    if pd.notna(val):
                        details[excel_col] = str(val).strip()

            # \u6b04\u4f4d\u6e05\u6d17
            if 'phone' in record:
                record['phone'] = clean_phone(record['phone'])
            if 'city' in record or 'address' in record:
                clean_c, clean_a = clean_city_and_address(record.get('city'), record.get('address'))
                record['city'] = clean_c
                record['address'] = clean_a

            # \u6e05\u6d17\u8207\u5408\u4f75\u51fa\u751f\u65e5\u671f
            birth_year = row.get('\u51fa\u751f\u5e74')
            birth_month = row.get('\u6708')
            birth_day = row.get('\u65e5')
            record['birth_date'] = clean_birth_date(birth_year, birth_month, birth_day)
            record['survey_details'] = json.dumps(details, ensure_ascii=False)

            query_no = record.get('query_no')
            existing_cnt = 0
            if query_no:
                cursor.execute(
                    "SELECT COUNT(*) AS existing_cnt FROM beclass_records WHERE query_no = %s",
                    (query_no,)
                )
                existing = cursor.fetchone()
                existing_cnt = int(existing['existing_cnt']) if existing and existing['existing_cnt'] is not None else 0
            if existing_cnt == 1:
                skipped_existing += 1
                conn.commit()
                _reconcile_without_rolling_back_beclass(conn, query_no)
                continue
            if existing_cnt > 1:
                review_required += 1
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.CLIENT,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.CLIENT,
                        query_no,
                        phone_for_alert,
                    ),
                    source_payload=_privacy_safe_client_review_payload(record),
                    issue_codes=("duplicate_query_no",),
                )
                conn.commit()
                continue
            if errors:
                review_required += 1
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.CLIENT,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.CLIENT,
                        query_no,
                        phone_for_alert,
                    ),
                    source_payload=_privacy_safe_client_review_payload(record),
                    issue_codes=tuple(errors),
                )
                conn.commit()
                continue

            cols = ", ".join([f"`{k}`" for k in record.keys()])
            places = ", ".join(["%s"] * len(record))
            sql = f"INSERT INTO beclass_records ({cols}) VALUES ({places})"
            cursor.execute(sql, tuple(record.values()))
            inserted += 1
            conn.commit()
            _reconcile_without_rolling_back_beclass(conn, query_no)

        conn.commit()
        print(
            f"\u532f\u5165\u5b8c\u6210\uff1a\u65b0\u589e {inserted} \u7b46\u5ba2\u6236 BeClass \u8cc7\u6599\uff0c"
            f"\u7565\u904e {skipped_existing} \u7b46\u3001\u9700\u5be9\u67e5 {review_required} \u7b46\u3002"
        )
    except Exception as err:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"\u57f7\u884c\u51fa\u932f\u5df2 Rollback\uff1a{err}")
        return _result(
            inserted=0,
            skipped_existing=skipped_existing,
            review_required=review_required,
            failed=1
        )
    finally:
        conn.close()

    return _result(inserted=inserted, skipped_existing=skipped_existing, review_required=review_required)


def _reconcile_without_rolling_back_beclass(connection, query_no):
    if not query_no:
        return "identity_conflict"
    try:
        result = reconcile_hcm_beclass_cooking(connection, str(query_no))
    except Exception as error:
        print(f"[配對待重試] BeClass root 已建立；reconciliation稍後重試：{type(error).__name__}")
        return "failed_retryable"
    print(f"[配對狀態] {result.status}")
    return result.status


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
        parser.add_argument("workbook")
        parsed = parser.parse_args(sys.argv[1:])
        from scripts.imports.historical_import_guard import authorize_historical_apply

        apply_arguments = [parsed.workbook]
        if parsed.historical_apply:
            apply_arguments.insert(0, "--historical-apply")
        excel_arg = authorize_historical_apply(apply_arguments, str(DB_CONFIG["database"]))
    except RuntimeError as error:
        print(f"歷史匯入已阻擋：{error}")
        raise SystemExit(2) from error
    process_import(excel_arg)

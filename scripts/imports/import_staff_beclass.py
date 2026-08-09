# -*- coding: utf-8 -*-
"""
Import staff BeClass Excel and write into:
staff + related option tables.
Insert-only behavior:
  - dedupe only by identity_card
  - existing identity_card -> skipped_existing
  - missing identity_card -> review_required
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Let file_watcher.py run this script as a subprocess with project imports available.
# Let file_watcher.py run this script as a subprocess with project imports available.
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
    from domains.case_import.staff_import_validation import (
        EXCEL_TO_DB_COLUMN,
        fallback_case_key,
        validate_staff_row,
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
from subsystems.anomalies.system_alert_projection import (
    delete_system_alert,
    resolve_if_exists,
    upsert_system_alert,
)
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.beclass_review_intake import (
    fingerprint_workbook,
    masked_review_identifier,
    record_invalid_beclass_row,
)

load_dotenv(str(PROJECT_ROOT / ".env"))

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'database': os.getenv('DB_DATABASE', 'union_db'),
    'charset': 'utf8mb4'
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
    city = city.replace("台", "臺")
    address = address.replace("台", "臺")

    if not city and len(address) >= 3:
        for pc in ["臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市", "基隆市", "新竹市", "嘉義市",
                   "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "花蓮縣", "宜蘭縣", "苗栗縣", "台東縣"]:
            if address.startswith(pc):
                city = pc
                break
    if city in ["臺北", "新北", "桃園", "臺中", "臺南", "高雄"]:
        city = city + "市"
    elif city in ["新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "花蓮", "宜蘭", "臺東", "基隆"]:
        city = city + "縣"
    return city, address


def clean_birth_date(year_val, month_val, day_val):
    if pd.isna(year_val) or pd.isna(month_val) or pd.isna(day_val):
        return None
    try:
        import datetime as dt
        y = int(year_val)
        m = int(month_val)
        d = int(day_val)
        if y < 1900:
            y += 1911
        return dt.date(y, m, d).strftime("%Y-%m-%d")
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


def import_checkbox_options(cursor, staff_id, row, options_list, target_table, value_col, detail_col=None, excel_detail_col=None):
    # Delete-and-insert strategy for option tables
    cursor.execute(f"DELETE FROM {target_table} WHERE staff_id = %s", (staff_id,))
    for opt in options_list:
        if row.get(opt) == 'Y':
            if detail_col:
                cursor.execute(
                    f"INSERT INTO {target_table} (staff_id, {value_col}, {detail_col}) VALUES (%s, %s, %s)",
                    (staff_id, opt, None)
                )
            else:
                cursor.execute(
                    f"INSERT INTO {target_table} (staff_id, {value_col}) VALUES (%s, %s)",
                    (staff_id, opt)
                )
    if excel_detail_col and detail_col:
        other_val = row.get(excel_detail_col)
        if pd.notna(other_val) and str(other_val).strip():
            cursor.execute(
                f"INSERT INTO {target_table} (staff_id, {value_col}, {detail_col}) VALUES (%s, %s, %s)",
                (staff_id, '其他', str(other_val).strip())
            )


def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)

    print(f"解析 Excel 檔案：{excel_path} ...")
    xl = pd.ExcelFile(excel_path)

    target_sheet = xl.sheet_names[0] if xl.sheet_names else None
    if target_sheet is None:
        print("未找到任何工作表，跳過此檔案。")
        return _result(review_required=1)

    df = xl.parse(target_sheet)
    if df.empty:
        for sheet_name in xl.sheet_names[1:]:
            candidate = xl.parse(sheet_name)
            if not candidate.empty:
                target_sheet = sheet_name
                df = candidate
                break

    if df is None or df.empty:
        print("未找到有資料的工作表，請確認檔案內容後重試。")
        return _result(review_required=1)
    source_content_digest = fingerprint_workbook(excel_path)
    print(f"找到工作表：'{target_sheet}'，共有 {len(df)} 筆資料，準備匯入...")

    try:
        conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()
        cursor.execute("SET NAMES utf8mb4;")
        conn.commit()
    except Exception as e:
        print(f"資料庫連線失敗：{e}")
        return _result(failed=1)

    inserted = 0
    skipped_existing = 0
    review_required = 0

    try:
        for source_row, (_, row) in enumerate(df.iterrows(), start=2):
            raw_row = row.to_dict()
            errors = validate_staff_row(raw_row)
            name_for_alert = raw_row.get('姓名')
            phone_for_alert = raw_row.get('行動電話')

            name = clean_data(row.get('姓名'), 'name')
            identity_card = clean_data(row.get('身分證字號'), 'identity_card')

            if not identity_card:
                review_required += 1
                err_detail = f" - 欄位錯誤: {'、'.join(errors.keys()) if isinstance(errors, dict) else errors}" if errors else ""
                print(f"[待確認警示] 第 {source_row} 列：查無身分證字號 (姓名: {name_for_alert or '未填'}, 電話: {phone_for_alert or '未填'}){err_detail}")
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.STAFF,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.STAFF,
                        identity_card,
                        phone_for_alert,
                    ),
                    source_payload={
                        "identity_card": None,
                        "name": clean_data(name_for_alert, "name"),
                        "phone": clean_phone(phone_for_alert),
                    },
                    issue_codes=tuple(errors),
                )
                if errors:
                    error_keys_joined = "、".join(errors.keys())
                    upsert_system_alert(
                        cursor,
                        alert_code="IMPORT-004",
                        source_domain="IMPORT",
                        case_key=fallback_case_key(name_for_alert, phone_for_alert),
                        reason=f"服務人員匯入資料異常（查無身分證字號）：{error_keys_joined}",
                        details=errors,
                    )
                continue

            if not name:
                # staff.name 是 NOT NULL，缺姓名時無法建立資料，只能開警示提醒補件
                review_required += 1
                print(f"[待確認警示] 第 {source_row} 列：缺少姓名 (身分證: {identity_card}, 電話: {phone_for_alert or '未填'})")
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.STAFF,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.STAFF,
                        identity_card,
                        phone_for_alert,
                    ),
                    source_payload={
                        "identity_card": identity_card,
                        "name": None,
                        "phone": clean_phone(phone_for_alert),
                    },
                    issue_codes=tuple(errors),
                )
                upsert_system_alert(
                    cursor,
                    alert_code="IMPORT-004",
                    source_domain="IMPORT",
                    case_key=identity_card,
                    reason=f"服務人員 {identity_card} 缺少姓名，無法建立資料",
                    details=errors,
                )
                continue

            ip_address = clean_data(row.get('IP位址'), 'ip_address')
            registered_at = None
            reg_val = row.get('報名時間')
            if pd.notna(reg_val):
                try:
                    registered_at = pd.to_datetime(reg_val).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    registered_at = str(reg_val).strip()

            birthday = None
            b_date_val = row.get('民國出生年月日')
            if pd.notna(b_date_val):
                try:
                    if isinstance(b_date_val, (datetime, pd.Timestamp)):
                        birthday = b_date_val.strftime("%Y-%m-%d")
                    else:
                        birthday = str(b_date_val).strip()[:10]
                except Exception:
                    pass
            if not birthday:
                birthday = clean_birth_date(row.get('出生年'), row.get('月'), row.get('日'))

            city, address = clean_city_and_address(row.get('縣市'), row.get('地址'))
            phone = clean_phone(row.get('行動電話'))

            has_massage_cert = False
            massage_val = row.get('有嬰幼兒按摩證書嗎?')
            if pd.notna(massage_val) and str(massage_val).strip() in ['有', 'Y', 'y', '1', 'True', 'true']:
                has_massage_cert = True

            care_babies = 1
            twin_val = row.get('雙胞胎')
            triplet_val = row.get('三胞胎')
            summary_val = str(row.get('可承接的胎數', '')) if pd.notna(row.get('可承接的胎數')) else ''

            if (pd.notna(triplet_val) and str(triplet_val).strip() in ['Y', 'y', '1', 'True', 'true']) or '三胞胎' in summary_val:
                care_babies = 3
            elif (pd.notna(twin_val) and str(twin_val).strip() in ['Y', 'y', '1', 'True', 'true']) or '雙胞胎' in summary_val:
                care_babies = 2

            record = {
                'registered_at': registered_at,
                'ip_address': ip_address,
                'name': name,
                'identity_card': identity_card,
                'phone': phone,
                'tel': clean_data(row.get('市話'), 'tel'),
                'tel_ext': clean_data(row.get('分機'), 'tel_ext'),
                'email': clean_data(row.get('EMAIL'), 'email'),
                'birthday': birthday,
                'city': city,
                'zip_code': clean_data(row.get('郵遞區號'), 'zip_code'),
                'address': address,
                'has_massage_cert': has_massage_cert,
                'care_babies': care_babies,
                'status': 'active'
            }

            cursor.execute(
                "SELECT name FROM staff WHERE identity_card = %s",
                (identity_card,)
            )
            existing_rows = cursor.fetchall()
            existing_cnt = len(existing_rows)
            if existing_cnt == 1:
                skipped_existing += 1
                existing_name = existing_rows[0]['name']
                if not existing_name or not name or existing_name == name:
                    continue
                review_required += 1
                print(f"[待確認警示] 第 {source_row} 列：身分證字號 {identity_card} 重複，但姓名不一致 (資料庫已有: 「{existing_name}」，本次匯入: 「{name}」)")
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.STAFF,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.STAFF,
                        identity_card,
                        phone_for_alert,
                    ),
                    source_payload=record,
                    issue_codes=("identity_name_mismatch",),
                )
                upsert_system_alert(
                    cursor,
                    alert_code="IMPORT-003",
                    source_domain="IMPORT",
                    case_key=identity_card,
                    reason=f"身分證字號 {identity_card} 重複，但姓名不一致：已存「{existing_name}」，本次匯入「{name}」",
                    details={"身分證字號": identity_card, "已存姓名": existing_name, "本次匯入姓名": name},
                )
                continue
            if existing_cnt > 1:
                review_required += 1
                print(f"[待確認警示] 第 {source_row} 列：身分證字號 {identity_card} 在資料庫中有多筆記錄 ({existing_cnt} 筆)")
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.STAFF,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.STAFF,
                        identity_card,
                        phone_for_alert,
                    ),
                    source_payload=record,
                    issue_codes=("duplicate_identity_card",),
                )
                continue
            if errors:
                review_required += 1
                err_msg = "、".join(errors.values()) if isinstance(errors, dict) else str(errors)
                print(f"[欄位已阻擋] 第 {source_row} 列：服務人員 (身分證: {identity_card}, 姓名: {name}) 欄位驗證異常 - {err_msg}")
                record_invalid_beclass_row(
                    conn,
                    source_kind=BeClassImportSourceKind.STAFF,
                    source_content_digest=source_content_digest,
                    source_sheet=target_sheet,
                    source_row=source_row,
                    masked_identifier=masked_review_identifier(
                        BeClassImportSourceKind.STAFF,
                        identity_card,
                        phone_for_alert,
                    ),
                    source_payload=record,
                    issue_codes=tuple(errors),
                )
                upsert_system_alert(
                    cursor,
                    alert_code="IMPORT-004",
                    source_domain="IMPORT",
                    case_key=identity_card,
                    reason=f"服務人員 {identity_card} 匯入資料異常：{'、'.join(errors)}",
                    details=errors,
                )
                for excel_column, database_column in EXCEL_TO_DB_COLUMN.items():
                    if excel_column in errors:
                        record[database_column] = None

            if existing_cnt == 0:
                cols = ", ".join([f"`{k}`" for k in record.keys()])
                places = ", ".join(["%s"] * len(record))
                sql = f"INSERT INTO staff ({cols}) VALUES ({places})"
                cursor.execute(sql, tuple(record.values()))
                staff_id = cursor.lastrowid
                inserted += 1

                bank_acc = clean_data(row.get('銀行帳號'), 'account_no')
                if bank_acc and "銀行代3碼+分行代號4碼" not in errors:
                    # 範例檔實際表頭是「銀行代3碼+分行代號4碼」(少一個「碼」字)，
                    # 這裡兩種寫法都認，避免之後樣板又改回另一種寫法時又讀不到。
                    bank_branch_raw = row.get('銀行代3碼+分行代號4碼')
                    if pd.isna(bank_branch_raw):
                        bank_branch_raw = row.get('銀行代碼3碼+分行代號4碼')
                    bank_branch = clean_data(bank_branch_raw, 'bank_branch')
                    bank_code = bank_branch[:3] if bank_branch and len(bank_branch) >= 3 else None
                    branch_code = bank_branch[3:] if bank_branch and len(bank_branch) > 3 else None
                    cursor.execute(
                        "INSERT INTO staff_bank_accounts (staff_id, bank_code, branch_code, account_no, is_primary) VALUES (%s, %s, %s, %s, %s)",
                        (staff_id, bank_code, branch_code, bank_acc, True)
                    )
                    add_acc = row.get('若有其它同銀行帳號，請一併提供。(永豐或台新)')
                    if pd.notna(add_acc) and str(add_acc).strip():
                        acc_clean = re.sub(r'\D', '', str(add_acc))
                        if len(acc_clean) >= 8:
                            cursor.execute(
                                "INSERT INTO staff_bank_accounts (staff_id, bank_code, branch_code, account_no, is_primary) VALUES (%s, %s, %s, %s, %s)",
                                (staff_id, None, None, acc_clean, False)
                            )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['北區', '東區', '香山區', '新竹縣', '苗栗縣'],
                    target_table='staff_regions',
                    value_col='region_name',
                    detail_col='custom_region_detail',
                    excel_detail_col='[其它].1'
                )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['4小時(上午8:30-12:30)', '4小時(下午13:00-17:00)', '8小時', '24小時'],
                    target_table='staff_time_slots',
                    value_col='slot_name',
                    detail_col='custom_slot_detail',
                    excel_detail_col='[其它].2'
                )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['葷食', '素食'],
                    target_table='staff_cooking_skills',
                    value_col='skill_name',
                    detail_col='custom_skill_detail',
                    excel_detail_col='[其它]'
                )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['機車', '轎車'],
                    target_table='staff_transportation',
                    value_col='vehicle_type'
                )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休'],
                    target_table='staff_holiday_availability',
                    value_col='holiday_name',
                    detail_col='custom_holiday_detail',
                    excel_detail_col='[其它].5'
                )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['連續服務', '週休1日', '週休2日'],
                    target_table='staff_weekly_rest',
                    value_col='rest_type',
                    detail_col='custom_rest_detail',
                    excel_detail_col='[其它].3'
                )

                import_checkbox_options(
                    cursor, staff_id, row,
                    options_list=['單胞胎', '雙胞胎'],
                    target_table='staff_baby_types',
                    value_col='baby_type',
                    detail_col='custom_baby_detail',
                    excel_detail_col='[其它].4'
                )

                # 有身分證字號了：若先前用 error_姓名_電話 這個替代鍵記錄過，就把舊的清掉
                fallback_key = fallback_case_key(name_for_alert, phone_for_alert)
                if not fallback_key.startswith("error_row_"):
                    delete_system_alert(cursor, alert_code="IMPORT-004", case_key=fallback_key)

                resolve_if_exists(
                    cursor,
                    alert_code="IMPORT-004",
                    case_key=identity_card,
                    reason="系統重新匯入：欄位驗證通過，自動解除",
                )

        conn.commit()
        print(
            f"匯入完成：新增 {inserted} 筆服務人員資料，"
            f"略過既有 {skipped_existing} 筆、待確認 {review_required} 筆。"
        )
    except Exception as err:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"執行發生錯誤，已 Rollback：{err}")
        return _result(
            inserted=0,
            skipped_existing=skipped_existing,
            review_required=review_required,
            failed=1
        )
    finally:
        conn.close()

    return _result(inserted=inserted, skipped_existing=skipped_existing, review_required=review_required)


if __name__ == "__main__":
    excel_arg = sys.argv[1] if len(sys.argv) > 1 else "document/資料庫、資料處理/假資料_模板.xlsx"
    process_import(excel_arg)

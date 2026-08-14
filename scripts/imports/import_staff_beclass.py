# -*- coding: utf-8 -*-
"""
File: import_staff_beclass.py
Description: 依 Staff BeClass 核心與替代欄位契約選表，驗證並匯入歷史人員資料。
"""
import argparse
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
        matches_staff_beclass_headers,
        staff_bank_branch_value,
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
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.beclass_review_intake import (
    fingerprint_workbook,
    masked_review_identifier,
    record_invalid_beclass_row,
)
from subsystems.case_import.staff_historical_adoption import (
    adopt_existing_staff,
    record_created_staff_adoption,
    record_staff_adoption_outcome,
)
from shared_kernel.fingerprints import fingerprint_payload
from infrastructure.mysql.staff_historical_workbook_repository import (
    MySqlStaffHistoricalWorkbookRepository,
)
from subsystems.case_import.staff_historical_workbook_adoption import (
    StaffHistoricalWorkbookConflict,
    StaffHistoricalWorkbookService,
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
            connection, MySqlStaffHistoricalWorkbookRepository(connection)
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


def _historical_bank_accounts(row, errors):
    account = clean_data(row.get('銀行帳號'), 'account_no')
    if not account or "銀行代3碼+分行代號4碼" in errors:
        return ()
    branch_raw = staff_bank_branch_value(row)
    branch = clean_data(branch_raw, 'bank_branch')
    bank_code = branch[:3] if branch and len(branch) >= 3 else None
    branch_code = branch[3:] if branch and len(branch) > 3 else None
    accounts = [(bank_code, branch_code, account, True)]
    additional = row.get('若有其它同銀行帳號，請一併提供。(永豐或台新)')
    if pd.notna(additional):
        digits = re.sub(r'\D', '', str(additional))
        if len(digits) >= 8:
            accounts.append((None, None, digits, False))
    return tuple(accounts)


def _historical_relations(row):
    specs = (
        ('staff_regions', ('北區', '東區', '香山區', '新竹縣', '苗栗縣'), '[其它].1'),
        ('staff_time_slots', ('4小時(上午8:30-12:30)', '4小時(下午13:00-17:00)', '8小時', '24小時'), '[其它].2'),
        ('staff_cooking_skills', ('葷食', '素食'), '[其它]'),
        ('staff_transportation', ('機車', '轎車'), None),
        ('staff_holiday_availability', ('年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休'), '[其它].5'),
        ('staff_weekly_rest', ('連續服務', '週休1日', '週休2日'), '[其它].3'),
        ('staff_baby_types', ('單胞胎', '雙胞胎'), '[其它].4'),
    )
    relations = {}
    for table_name, options, other_column in specs:
        values = [(option, None) for option in options if row.get(option) == 'Y']
        if other_column:
            other = row.get(other_column)
            if pd.notna(other) and str(other).strip():
                values.append(('其他', str(other).strip()))
        if table_name == 'staff_transportation':
            values = [(value[0],) for value in values]
        relations[table_name] = tuple(values)
    return relations


def process_import(excel_path, source_revision: str | None = None):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)
    return _typed_historical_import(excel_path, source_revision)


def _legacy_process_import_not_used(excel_path, source_revision: str | None = None):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return _result(review_required=1)

    selected = _load_staff_beclass_frame(excel_path)
    if selected is None:
        return _result(review_required=1)
    target_sheet, df = selected
    source_content_digest = _staff_source_content_digest(excel_path, source_revision)
    print(f"已依欄位契約選取工作表，共有 {len(df)} 筆資料，準備匯入...")

    try:
        conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()
        cursor.execute("SET NAMES utf8mb4;")
        conn.commit()
    except Exception as e:
        print(f"資料庫連線失敗：{e}")
        return _result(failed=1)

    inserted = 0
    adopted_existing = 0
    exact_replay = 0
    blocked_identity = 0
    identity_conflict = 0
    review_required = 0

    try:
        for source_row, (_, row) in enumerate(df.iterrows(), start=2):
            raw_row = row.to_dict()
            errors = validate_staff_row(raw_row)
            name_for_alert = raw_row.get('姓名')
            phone_for_alert = raw_row.get('行動電話')

            name = clean_data(row.get('姓名'), 'name')
            identity_card = clean_data(row.get('身分證字號'), 'identity_card')

            if not identity_card or "身分證字號" in errors:
                review_required += 1
                issue_fields = "、".join(sorted(errors)) if isinstance(errors, dict) else "identity"
                print(f"[待確認警示] 第 {source_row} 列：blocked identity；欄位={issue_fields}")
                review_identity = record_invalid_beclass_row(
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
                    source_payload=_privacy_safe_staff_review_payload(
                        {"identity_card": None, "name": name_for_alert, "phone": phone_for_alert}
                    ),
                    issue_codes=tuple(errors),
                )
                replayed = record_staff_adoption_outcome(
                    conn,
                    source_content_digest=source_content_digest,
                    source_row=source_row,
                    staff_id=None,
                    historical_record={"identity_card": None, "name": name, "phone": clean_phone(phone_for_alert)},
                    review_identity=review_identity,
                    outcome="blocked_identity",
                )
                exact_replay += int(replayed)
                blocked_identity += int(not replayed)
                conn.commit()
                continue

            if not name or "姓名" in errors:
                # staff.name 是 NOT NULL，缺姓名時無法建立資料，只能開警示提醒補件
                review_required += 1
                print(f"[待確認警示] 第 {source_row} 列：缺少姓名；識別={masked_review_identifier(BeClassImportSourceKind.STAFF, identity_card, source_row)}")
                review_identity = record_invalid_beclass_row(
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
                    source_payload=_privacy_safe_staff_review_payload(
                        {"identity_card": identity_card, "name": None, "phone": phone_for_alert}
                    ),
                    issue_codes=tuple(errors),
                )
                replayed = record_staff_adoption_outcome(
                    conn,
                    source_content_digest=source_content_digest,
                    source_row=source_row,
                    staff_id=None,
                    historical_record={"identity_card": identity_card, "name": None, "phone": clean_phone(phone_for_alert)},
                    review_identity=review_identity,
                    outcome="blocked_identity",
                )
                exact_replay += int(replayed)
                blocked_identity += int(not replayed)
                conn.commit()
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

            if errors:
                for excel_column, database_column in EXCEL_TO_DB_COLUMN.items():
                    if excel_column in errors:
                        record[database_column] = None

            cursor.execute(
                "SELECT id,name FROM staff WHERE identity_card = %s",
                (identity_card,)
            )
            existing_rows = cursor.fetchall()
            existing_cnt = len(existing_rows)
            if existing_cnt == 1:
                existing_name = existing_rows[0]['name']
                if existing_name and name and existing_name != name:
                    review_required += 1
                    review_identity = record_invalid_beclass_row(
                        conn,
                        source_kind=BeClassImportSourceKind.STAFF,
                        source_content_digest=source_content_digest,
                        source_sheet=target_sheet,
                        source_row=source_row,
                        masked_identifier=masked_review_identifier(
                            BeClassImportSourceKind.STAFF, identity_card, phone_for_alert
                        ),
                        source_payload=_privacy_safe_staff_review_payload(record),
                        issue_codes=("identity_name_mismatch",),
                    )
                    replayed = record_staff_adoption_outcome(
                        conn,
                        source_content_digest=source_content_digest,
                        source_row=source_row,
                        staff_id=int(existing_rows[0]["id"]),
                        historical_record=record,
                        review_identity=review_identity,
                        outcome="identity_conflict",
                    )
                    exact_replay += int(replayed)
                    identity_conflict += int(not replayed)
                    conn.commit()
                    continue
                adoption = adopt_existing_staff(
                    conn,
                    source_content_digest=source_content_digest,
                    source_row=source_row,
                    identity_card=identity_card,
                    historical_record=record,
                    source_sheet=target_sheet,
                    review_payload=_privacy_safe_staff_review_payload(record),
                    validation_issue_codes=tuple(
                        f"staff_field_invalid:{field}" for field in sorted(errors)
                    ),
                    bank_accounts=_historical_bank_accounts(row, errors),
                    relations=_historical_relations(row),
                )
                if adoption.replayed:
                    exact_replay += 1
                elif adoption.outcome == "adopted_existing":
                    adopted_existing += 1
                elif adoption.outcome == "blocked_identity":
                    blocked_identity += 1
                elif adoption.outcome == "identity_conflict":
                    identity_conflict += 1
                if errors or adoption.conflict_fields or adoption.outcome in {
                    "blocked_identity",
                    "identity_conflict",
                }:
                    review_required += 1
                continue
            if existing_cnt > 1:
                review_required += 1
                print(f"[待確認警示] 第 {source_row} 列：identity conflict ({existing_cnt} 筆)")
                review_identity = record_invalid_beclass_row(
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
                    source_payload=_privacy_safe_staff_review_payload(record),
                    issue_codes=("duplicate_identity_card",),
                )
                replayed = record_staff_adoption_outcome(
                    conn,
                    source_content_digest=source_content_digest,
                    source_row=source_row,
                    staff_id=None,
                    historical_record=record,
                    review_identity=review_identity,
                    outcome="identity_conflict",
                )
                exact_replay += int(replayed)
                identity_conflict += int(not replayed)
                conn.commit()
                continue
            row_review_identity = None
            if errors:
                review_required += 1
                issue_fields = "、".join(sorted(errors)) if isinstance(errors, dict) else "validation"
                print(f"[待確認警示] 第 {source_row} 列：欄位驗證異常；欄位={issue_fields}")
                row_review_identity = record_invalid_beclass_row(
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
                    source_payload=_privacy_safe_staff_review_payload(record),
                    issue_codes=tuple(errors),
                )
            if existing_cnt == 0:
                cols = ", ".join([f"`{k}`" for k in record.keys()])
                places = ", ".join(["%s"] * len(record))
                sql = f"INSERT INTO staff ({cols}) VALUES ({places})"
                cursor.execute(sql, tuple(record.values()))
                staff_id = cursor.lastrowid
                inserted += 1

                bank_acc = clean_data(row.get('銀行帳號'), 'account_no')
                if bank_acc and "銀行代3碼+分行代號4碼" not in errors:
                    bank_branch_raw = staff_bank_branch_value(row)
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

                record_created_staff_adoption(
                    conn,
                    source_content_digest=source_content_digest,
                    source_row=source_row,
                    staff_id=staff_id,
                    historical_record=record,
                    review_identity=row_review_identity,
                )

                conn.commit()

        conn.commit()
        print(
            f"匯入完成：source rows {len(df)}，新增 {inserted}，採納既有 {adopted_existing}，"
            f"exact replay {exact_replay}，blocked identity {blocked_identity}，"
            f"identity conflict {identity_conflict}，review required {review_required}。"
        )
    except Exception as err:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"目前來源列失敗並已回滾；先前已提交的 terminal rows 保留：{err}")
        return _result(
            inserted=inserted,
            adopted_existing=adopted_existing,
            exact_replay=exact_replay,
            blocked_identity=blocked_identity,
            identity_conflict=identity_conflict,
            review_required=review_required,
            failed=1
        )
    finally:
        conn.close()

    return _result(
        inserted=inserted,
        adopted_existing=adopted_existing,
        exact_replay=exact_replay,
        blocked_identity=blocked_identity,
        identity_conflict=identity_conflict,
        review_required=review_required,
    )


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


def _parse_historical_staff_arguments(arguments: list[str]) -> tuple[str, str | None]:
    parser = argparse.ArgumentParser(description="Staff BeClass 歷史資料受控匯入")
    parser.add_argument("--historical-apply", action="store_true")
    parser.add_argument("--source-revision")
    parser.add_argument("workbook")
    parsed = parser.parse_args(arguments)
    from scripts.imports.historical_import_guard import authorize_historical_apply

    apply_arguments = [parsed.workbook]
    if parsed.historical_apply:
        apply_arguments.insert(0, "--historical-apply")
    workbook = authorize_historical_apply(apply_arguments, str(DB_CONFIG["database"]))
    return workbook, parsed.source_revision


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
        excel_arg, source_revision_arg = _parse_historical_staff_arguments(sys.argv[1:])
    except RuntimeError as error:
        print(f"歷史匯入已阻擋：{error}")
        raise SystemExit(2) from error
    process_import(excel_arg, source_revision=source_revision_arg)

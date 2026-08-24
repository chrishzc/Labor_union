"""
File: mysql_adapter.py
Description: 提供既有 MySQL 存取與服務日精算 adapter；人工服務日只覆蓋固定週休。
"""

import os
import json
import re
import pymysql
import math
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# 從專案根目錄的 .env 讀取資料庫連線設定 (若 .env 不存在或缺少某欄位，則回退為原本的預設值)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

DEVELOPMENT_GCE_IAP_BRIDGE_PROFILE = "development_gce_iap_reverse_ssh"


def _database_config_from_environment() -> dict:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    deployment_profile = os.getenv("DEPLOYMENT_PROFILE", "").strip().lower()
    if app_env == "production" and deployment_profile == DEVELOPMENT_GCE_IAP_BRIDGE_PROFILE:
        raise RuntimeError(
            "development GCE+IAP reverse SSH DB bridge is forbidden in production"
        )

    config = {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "1234"),
        "database": os.getenv("DB_DATABASE", "union_db"),
        "charset": "utf8mb4",
    }
    ssl_mode = os.getenv("DB_SSL_MODE", "disabled").strip().lower()
    if ssl_mode == "disabled":
        return config
    if ssl_mode not in {"verify_ca", "verify_identity"}:
        raise RuntimeError("DB_SSL_MODE must be disabled, verify_ca, or verify_identity")
    ca_path = os.getenv("DB_SSL_CA", "").strip()
    cert_path = os.getenv("DB_SSL_CERT", "").strip()
    key_path = os.getenv("DB_SSL_KEY", "").strip()
    if not all((ca_path, cert_path, key_path)):
        raise RuntimeError("MySQL mTLS requires DB_SSL_CA, DB_SSL_CERT, and DB_SSL_KEY")
    config["ssl"] = {
        "ca": ca_path,
        "cert": cert_path,
        "key": key_path,
        "check_hostname": ssl_mode == "verify_identity",
    }
    return config


DB_CONFIG = _database_config_from_environment()

def safe_float(val) -> float:
    if val is None:
        return 0.0
    try:
        f = float(val)
        return 0.0 if math.isnan(f) or math.isinf(f) else f
    except:
        return 0.0

def safe_int(val) -> int:
    """安全轉換整數，防護 None, NaN, Inf 及無效字串 (ADR-v18-03)"""
    if val is None:
        return 0
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return 0
        return int(round(f))
    except:
        return 0

def safe_date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if hasattr(val, "date"):
        return val
    if isinstance(val, (str, bytes)):
        try:
            clean_str = str(val).split(" ")[0].strip()
            return datetime.strptime(clean_str, "%Y-%m-%d").date()
        except:
            return None
    return val

def generate_virtual_account(case_no) -> str:
    """Build a 14-digit account only from one canonical nine-digit case number."""
    case_no_text = str(case_no) if case_no is not None else ""
    if len(case_no_text) != 9 or not case_no_text.isascii() or not case_no_text.isdigit():
        return ""

    roc_year = case_no_text[:3]
    sequence = int(case_no_text[3:])
    return f"99781699{roc_year}{sequence:03d}"

def get_connection():
    """建立並回傳資料庫連線"""
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def _resolve_case_no(case_ref) -> str:
    """Normalize the canonical case number used by every order operation."""
    case_no = str(case_ref or "").strip()
    if not case_no:
        raise ValueError("case_no 不可為空")
    return case_no


def get_order_by_case_no(case_no: str) -> dict | None:
    """Fetch the unique order identified by case_no."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.case_no, o.client_id, o.staff_id, o.status, o.cancel_reason,
                       o.line_group_id, o.actual_start_date, o.actual_end_date,
                       o.contract_identity, o.service_days, o.service_hours_per_day,
                       o.floor_fee, o.deposit_date,
                       o.start_date, o.end_date, o.custom_rest_dates,
                       o.created_at, o.updated_at,
                       c.name AS client_name, c.identity_status AS identity_status,
                       s.name AS staff_name
                FROM orders o
                JOIN clients c ON c.case_no = o.case_no
                LEFT JOIN staff s ON s.id = o.staff_id
                WHERE o.case_no = %s
            """, (_resolve_case_no(case_no),))
            return cursor.fetchone()
    finally:
        conn.close()

def get_table_data(table_name: str) -> list[dict]:
    """讀取指定原始資料表的內容"""
    allowed_tables = [
        'clients',
        'orders',
        'beclass_records',
        'matching_records',
        'holidays',
        'staff',
        'staff_bank_accounts',
        'case_staff_assignments',
        'client_payments',
        'client_payment_transactions',
        'actual_hours_adjustments',
        'staff_payments',
        'staff_payment_transactions',
        'payment_migration_reviews',
        'staff_schedule',
        'staff_regions',
        'staff_cooking_skills',
        'staff_weekly_rest',
        'staff_time_slots',
        'staff_transportation',
        'staff_holiday_availability',
        'staff_baby_types',
        'line_confirmation_requests',
        'staff_bookings',
    ]
    if table_name not in allowed_tables:
        raise ValueError(f"不允許查詢此資料表: {table_name}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if table_name == 'orders':
                cursor.execute("""
                    SELECT o.case_no, o.client_id, o.staff_id, o.status, o.cancel_reason,
                           o.line_group_id, o.actual_start_date, o.actual_end_date,
                           o.contract_identity, o.service_days, o.service_hours_per_day,
                           o.floor_fee, o.deposit_date, o.start_date, o.end_date,
                           o.custom_rest_dates, o.created_at, o.updated_at,
                           c.identity_status AS identity_status, s.name AS staff_name
                    FROM orders o
                    JOIN clients c ON c.case_no = o.case_no
                    LEFT JOIN staff s ON o.staff_id = s.id
                """)
            elif table_name == 'staff':
                cursor.execute("SELECT * FROM `staff`")
                rows = cursor.fetchall()

                cursor.execute("SELECT staff_id, region_name, custom_region_detail FROM staff_regions")
                region_rows = cursor.fetchall()
                region_map = {}
                for row in region_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    region_map.setdefault(sid, [])
                    if row.get('region_name'):
                        region_map[sid].append(row.get('region_name'))
                    if row.get('custom_region_detail'):
                        region_map[sid].append(f"其他：{row['custom_region_detail']}")

                cursor.execute("SELECT staff_id, skill_name, custom_skill_detail FROM staff_cooking_skills")
                skill_rows = cursor.fetchall()
                skill_map = {}
                for row in skill_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    skill_map.setdefault(sid, [])
                    if row.get('skill_name'):
                        skill_map[sid].append(row.get('skill_name'))
                    if row.get('custom_skill_detail'):
                        skill_map[sid].append(f"其他：{row['custom_skill_detail']}")

                cursor.execute("SELECT staff_id, rest_type FROM staff_weekly_rest")
                rest_rows = cursor.fetchall()
                rest_map = {}
                for row in rest_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    rest_map.setdefault(sid, [])
                    rest_map[sid].append(row.get('rest_type'))

                cursor.execute("SELECT staff_id, slot_name, custom_slot_detail FROM staff_time_slots")
                slot_rows = cursor.fetchall()
                slot_map = {}
                for row in slot_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    slot_map.setdefault(sid, [])
                    if row.get('slot_name'):
                        slot_map[sid].append(row.get('slot_name'))
                    if row.get('custom_slot_detail'):
                        slot_map[sid].append(f"其他：{row['custom_slot_detail']}")

                cursor.execute("SELECT staff_id, vehicle_type FROM staff_transportation")
                transport_rows = cursor.fetchall()
                transport_map = {}
                for row in transport_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    transport_map.setdefault(sid, [])
                    if row.get('vehicle_type'):
                        transport_map[sid].append(row.get('vehicle_type'))

                cursor.execute("SELECT staff_id, holiday_name, custom_holiday_detail FROM staff_holiday_availability")
                holiday_rows = cursor.fetchall()
                holiday_map = {}
                for row in holiday_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    holiday_map.setdefault(sid, [])
                    if row.get('holiday_name'):
                        holiday_map[sid].append(row.get('holiday_name'))
                    if row.get('custom_holiday_detail'):
                        holiday_map[sid].append(f"其他：{row['custom_holiday_detail']}")

                cursor.execute("SELECT staff_id, baby_type, custom_baby_detail FROM staff_baby_types")
                baby_rows = cursor.fetchall()
                baby_map = {}
                for row in baby_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    baby_map.setdefault(sid, [])
                    if row.get('baby_type'):
                        baby_map[sid].append(row.get('baby_type'))
                    if row.get('custom_baby_detail'):
                        baby_map[sid].append(f"其他：{row['custom_baby_detail']}")

                cursor.execute("SELECT staff_id, bank_code, branch_code, account_no, is_primary FROM staff_bank_accounts")
                bank_rows = cursor.fetchall()
                bank_map = {}
                for row in bank_rows:
                    sid = row.get('staff_id')
                    if sid is None:
                        continue
                    bank_map.setdefault(sid, [])
                    bank_parts = []
                    if row.get('bank_code'):
                        bank_parts.append(row.get('bank_code'))
                    if row.get('branch_code'):
                        bank_parts.append(row.get('branch_code'))
                    if row.get('account_no'):
                        bank_parts.append(row.get('account_no'))
                    suffix = "/".join(bank_parts) if bank_parts else str(row.get('account_no') or "")
                    bank_label = f"{'主帳戶' if row.get('is_primary') else '次要帳戶'}: {suffix}" if suffix else ('主帳戶' if row.get('is_primary') else '次要帳戶')
                    bank_map[sid].append(bank_label)

                for row in rows:
                    sid = row.get('id')
                    if sid is None:
                        continue

                    regions = [item for item in region_map.get(sid, []) if item]
                    if regions:
                        row['service_regions'] = json.dumps(list(dict.fromkeys(regions)), ensure_ascii=False)
                    else:
                        row['service_regions'] = json.dumps([], ensure_ascii=False)

                    skills = [item for item in skill_map.get(sid, []) if item]
                    if skills:
                        row['special_skills'] = json.dumps(list(dict.fromkeys(skills)), ensure_ascii=False)
                    else:
                        row['special_skills'] = json.dumps([], ensure_ascii=False)

                    rest_days = []
                    rest_items = rest_map.get(sid, [])
                    for rest_type in rest_items:
                        if rest_type in ('週休一日', '週休1日'):
                            if 'Sunday' not in rest_days:
                                rest_days.append('Sunday')
                        elif rest_type in ('週休二日', '週休2日'):
                            for day in ('Saturday', 'Sunday'):
                                if day not in rest_days:
                                    rest_days.append(day)
                    row['weekly_rest_days'] = json.dumps(rest_days, ensure_ascii=False)

                    time_slots = [item for item in slot_map.get(sid, []) if item]
                    if time_slots:
                        row['service_time_slots'] = json.dumps(list(dict.fromkeys(time_slots)), ensure_ascii=False)
                    else:
                        row['service_time_slots'] = json.dumps([], ensure_ascii=False)

                    transports = [item for item in transport_map.get(sid, []) if item]
                    if transports:
                        row['transportation_preferences'] = json.dumps(list(dict.fromkeys(transports)), ensure_ascii=False)
                    else:
                        row['transportation_preferences'] = json.dumps([], ensure_ascii=False)

                    holiday_preferences = [item for item in holiday_map.get(sid, []) if item]
                    if holiday_preferences:
                        row['holiday_preferences'] = json.dumps(list(dict.fromkeys(holiday_preferences)), ensure_ascii=False)
                    else:
                        row['holiday_preferences'] = json.dumps([], ensure_ascii=False)

                    baby_preferences = [item for item in baby_map.get(sid, []) if item]
                    if baby_preferences:
                        row['baby_type_preferences'] = json.dumps(list(dict.fromkeys(baby_preferences)), ensure_ascii=False)
                    else:
                        row['baby_type_preferences'] = json.dumps([], ensure_ascii=False)

                    bank_accounts = [item for item in bank_map.get(sid, []) if item]
                    if bank_accounts:
                        row['bank_accounts'] = json.dumps(list(dict.fromkeys(bank_accounts)), ensure_ascii=False)
                    else:
                        row['bank_accounts'] = json.dumps([], ensure_ascii=False)

                return rows
            else:
                cursor.execute(f"SELECT * FROM `{table_name}`")
            return cursor.fetchall()
    finally:
        conn.close()


def get_table_columns(table_name: str) -> list[str]:
    """取得指定資料表欄位名稱（用於無資料時仍可顯示欄位資訊）"""
    allowed_tables = [
        'clients',
        'orders',
        'beclass_records',
        'matching_records',
        'holidays',
        'staff',
        'staff_bank_accounts',
        'case_staff_assignments',
        'client_payments',
        'client_payment_transactions',
        'actual_hours_adjustments',
        'staff_payments',
        'staff_payment_transactions',
        'payment_migration_reviews',
        'staff_schedule',
        'staff_regions',
        'staff_cooking_skills',
        'staff_weekly_rest',
        'staff_time_slots',
        'staff_transportation',
        'staff_holiday_availability',
        'staff_baby_types',
        'line_confirmation_requests',
        'staff_bookings',
    ]
    if table_name not in allowed_tables:
        raise ValueError(f"不允許查詢此資料表: {table_name}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if table_name == 'staff':
                # staff 畫面會額外聚合顯示下列欄位，保留可視欄位一致性
                cursor.execute("SHOW COLUMNS FROM `staff`")
                rows = cursor.fetchall()
                base_cols = [row.get('Field') for row in rows if row.get('Field')]
                extra_cols = [
                    'service_regions',
                    'special_skills',
                    'weekly_rest_days',
                    'service_time_slots',
                    'transportation_preferences',
                    'holiday_preferences',
                    'baby_type_preferences',
                    'bank_accounts',
                ]
                return base_cols + [col for col in extra_cols if col not in base_cols]

            cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
            rows = cursor.fetchall()
            return [row.get('Field') for row in rows if row.get('Field')]
    finally:
        conn.close()

# 資料庫原始資料瀏覽頁面 (01_data_browser.py) 專用：可即時編輯資料表的主鍵欄位對照
# holidays 使用 holiday_date 作為主鍵，其餘資料表皆使用自增 id 作為主鍵
TABLE_PRIMARY_KEYS = {
    'clients': 'id',
    'staff': 'id',
    'orders': 'case_no',
    'beclass_records': 'id',
    'matching_records': 'id',
    'holidays': 'holiday_date',
    'staff_bank_accounts': 'id',
    'staff_regions': 'staff_id',
    'staff_cooking_skills': 'staff_id',
    'staff_weekly_rest': 'staff_id',
    'staff_time_slots': 'staff_id',
    'staff_transportation': 'staff_id',
    'staff_holiday_availability': 'staff_id',
    'staff_baby_types': 'staff_id',
    'line_confirmation_requests': 'id',
    'staff_bookings': 'id',
    'case_staff_assignments': 'id',
    'client_payments': 'id',
    'client_payment_transactions': 'id',
    'actual_hours_adjustments': 'id',
    'staff_payments': 'id',
    'staff_payment_transactions': 'id',
    'payment_migration_reviews': 'id',
    'staff_schedule': 'id',
}

_READONLY_SUBTABLES = {
    'staff_regions',
    'staff_cooking_skills',
    'staff_weekly_rest',
    'staff_time_slots',
    'staff_transportation',
    'staff_holiday_availability',
    'staff_baby_types',
}

# 系統自動管理欄位，一律唯讀，不允許透過即時編輯表格寫入，避免破壞主鍵/去重與時間戳記追蹤
READONLY_SYSTEM_COLUMNS = {
    'id', 'db_created_at', 'db_updated_at', 'created_at', 'updated_at',
    'sent_at', 'replied_at',
}

import json

def parse_beclass_survey_details(raw_val) -> dict:
    """自動解析 beclass_records.survey_details JSON 字串，提取 15 大照護細節 (INV-SVC-03)"""
    res = {
        "dietary_habits": "葷食、可以接受中藥補品：茶飲/藥飲/藥膳",
        "vegetarian_preference": "無法接受 (需確定為葷食月嫂)",
        "alcohol_ratio": "半酒",
        "cooking_oil_type": "苦茶油(前兩週)、麻油(後兩週)、一般食用油",
        "maternal_allergy": "無過敏體質",
        "special_care_notes": "依需求協助產婦與新生兒照顧",
        "meal_preferences": "清淡少鹽，口味不想重複",
        "cooking_tools": "炒菜鍋、大同電鍋、微波爐、烤箱、熱奶器、消毒鍋",
        "bath_water_prep": "中藥包煮沸",
        "breastfeeding_method": "母乳 + 配方奶混合哺育",
        "holiday_pricing_terms": "國定三節按合約規定支付 1 倍加班薪資",
        "multi_birth_count": "單胞胎",
        "stair_floor_fee_mode": "大樓電梯公寓 (無額外樓層費)",
        "parking_space_provided": "有提供專用轎車停車位",
        "other_babies_present": "無其他大寶同住"
    }
    if not raw_val:
        return res
        
    data = {}
    if isinstance(raw_val, dict):
        data = raw_val
    elif isinstance(raw_val, str):
        try:
            data = json.loads(raw_val)
        except Exception:
            return res

    normalized_data = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normal_key = re.sub(r"[\\s\\u00a0]+", "", key).replace("：", ":").replace("．", ".").lower()
        if normal_key:
            normalized_data[normal_key] = str(value)

    def _pick(options: list[str], default_value: str) -> str:
        for key in options:
            normal_key = re.sub(r"[\\s\\u00a0]+", "", key).replace("：", ":").replace("．", ".").lower()
            if normal_key in normalized_data:
                value = normalized_data[normal_key]
                if value is None:
                    continue
                return str(value)
        return default_value

    res["dietary_habits"] = _pick([
        "月子餐點調理喜好/飲食習慣",
        "月子餐點調理喜好/飲食習慣:",
    ], res["dietary_habits"])

    res["vegetarian_preference"] = _pick([
        "呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？",
    ], res["vegetarian_preference"])

    res["alcohol_ratio"] = _pick([
        "2.餐飲含酒比例:",
        "2．餐飲含酒比例:",
    ], res["alcohol_ratio"])

    res["cooking_oil_type"] = _pick([
        "3.料理用油:(可接受種類)",
        "3．料理用油:(可接受種類)",
    ], res["cooking_oil_type"])

    res["maternal_allergy"] = _pick([
        "5媽咪有無過敏體質:",
        "5.媽咪有無過敏體質:",
        "5．媽咪有無過敏體質:",
    ], res["maternal_allergy"])

    res["special_care_notes"] = _pick([
        "特殊照護時應注意事項:",
        "特殊照護時應注意事項",
    ], res["special_care_notes"])

    res["meal_preferences"] = _pick([
        "餐點喜忌備註:",
        "餐點喜忌備註",
    ], res["meal_preferences"])

    res["cooking_tools"] = _pick([
        "烹煮工具",
    ], res["cooking_tools"])

    res["bath_water_prep"] = _pick([
        "洗澡水準備:",
        "洗澡水準備",
    ], res["bath_water_prep"])

    res["breastfeeding_method"] = _pick([
        "哺乳方式:",
        "哺乳方式",
    ], res["breastfeeding_method"])

    res["holiday_pricing_terms"] = _pick([
        "特殊計費:甲方同意需另支付當日薪資1倍予乙方。",
    ], res["holiday_pricing_terms"])

    res["multi_birth_count"] = _pick([
        "特殊計費:胎數",
    ], res["multi_birth_count"])

    res["stair_floor_fee_mode"] = _pick([
        "透天服務樓層方式(會加收樓層費)",
    ], res["stair_floor_fee_mode"])

    res["parking_space_provided"] = _pick([
        "提供服務人員轎車停車位",
    ], res["parking_space_provided"])

    res["other_babies_present"] = _pick([
        "服務時間內是否有其他寶寶",
    ], res["other_babies_present"])
        
    return res

def get_order_details() -> list[dict]:
    """讀取 v_order_details 整合計算檢視表 (完全對齊 36 項業務與 15 大照護細節全圖譜)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 嘗試讀取 beclass_records survey_details 進行關聯
            survey_map = {}
            try:
                cursor.execute("SELECT query_no, survey_details FROM beclass_records WHERE survey_details IS NOT NULL")
                b_rows = cursor.fetchall()
                for br in b_rows:
                    if br.get('query_no') and br.get('survey_details'):
                        survey_map[str(br['query_no']).strip()] = parse_beclass_survey_details(br['survey_details'])
            except Exception:
                pass

            cursor.execute("SELECT * FROM v_order_details")
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT csa.case_no,
                       GROUP_CONCAT(
                           s.name ORDER BY csa.assignment_sequence
                           SEPARATOR '、'
                       ) AS assignment_staff_names
                  FROM case_staff_assignments csa
                  JOIN staff s ON s.id = csa.staff_id
                 WHERE csa.status <> 'cancelled'
                 GROUP BY csa.case_no
                """
            )
            assignment_staff_names = {
                str(row["case_no"]): row.get("assignment_staff_names")
                for row in (cursor.fetchall() or [])
                if row.get("case_no")
            }
            for r in rows:
                assignment_names = assignment_staff_names.get(
                    str(r.get("case_no") or "")
                )
                if assignment_names:
                    r["staff_name"] = assignment_names
                r['notes'] = r.get('notes') or r.get('special_needs') or ""
                def to_str_date(val):
                    if not val:
                        return ""
                    if hasattr(val, "strftime"):
                        return val.strftime("%Y-%m-%d")
                    return str(val)

                r['due_date'] = to_str_date(r.get('due_date') or r.get('start_date'))
                # 實際服務日期不可用預期日期補值，否則尚未開工的訂單會被誤判。
                r['actual_start_date'] = to_str_date(r.get('actual_start_date'))
                r['actual_end_date'] = to_str_date(r.get('actual_end_date'))
                r['deposit_received_at'] = to_str_date(r.get('deposit_received_at') or r.get('deposit_date'))
                r['start_date'] = to_str_date(r.get('start_date'))
                r['end_date'] = to_str_date(r.get('end_date'))
                r['deposit_date'] = to_str_date(r.get('deposit_date'))
                r['govt_claim_date'] = to_str_date(r.get('govt_claim_date'))

                r['custom_leave_dates'] = r.get('custom_leave_dates') or ""
                r['service_mode'] = r.get('service_mode') or "週休1日"
                r['service_hours_per_day'] = safe_int(r.get('service_hours_per_day', 9))
                days = safe_int(r.get('service_days', 20))
                hrs = safe_int(r.get('service_hours_per_day', 9))
                r['total_hours'] = r.get('total_hours') or (days * hrs)
                r['subsidy_hours'] = r.get('subsidy_hours') or (40 if r.get('identity_status') != '一般身分' else 0)
                r['self_pay_hours'] = max(0, r['total_hours'] - r['subsidy_hours'])
                r['claim_total_days'] = days
                r['employer_hourly_rate'] = r.get('employer_hourly_rate') or 2000
                r['deposit_days'] = r.get('deposit_days') or 1
                r['first_payment_days'] = r.get('first_payment_days') or safe_int(days / 2)
                r['second_payment_days'] = r.get('second_payment_days') or (days - r['first_payment_days'])
                r['caregiver_rate'] = r.get('caregiver_rate') or 2000
                
                end_dt = safe_date(r['actual_end_date'])
                if end_dt:
                    m1 = end_dt.month % 12 + 1
                    y1 = end_dt.year + (1 if end_dt.month == 12 else 0)
                    default_pay1 = f"{y1:04d}-{m1:02d}-15"
                    
                    m2 = m1 % 12 + 1
                    y2 = y1 + (1 if m1 == 12 else 0)
                    default_pay2 = f"{y2:04d}-{m2:02d}-15"
                else:
                    default_pay1 = "2026-10-15"
                    default_pay2 = "2026-11-15"

                r['salary_payment_date_1'] = to_str_date(r.get('salary_payment_date_1') or default_pay1)
                r['salary_payment_date_2'] = to_str_date(r.get('salary_payment_date_2') or default_pay2)
                r['phone'] = r.get('phone') or r.get('client_phone') or "0912-345-678"
                r['address'] = r.get('address') or r.get('client_address') or "新竹市東區中央路 100 號"
                r['total_caregiver_salary'] = safe_int(r.get('service_salary', 0)) + safe_int(r.get('subsidy_salary', 0))

                # 注入解包出來的 15 大照護細節欄位
                c_details = survey_map.get(str(r.get('case_no') or '').strip(), {})
                for dk, dv in c_details.items():
                    r[dk] = dv

            return rows
    finally:
        conn.close()


def get_case_order_details() -> list[dict]:
    """Return order view rows identified by case_no."""
    return get_order_details()


def get_staff_monthly_schedule(staff_id: int, year: int, month: int) -> dict[int, dict]:
    """
    獲取月嫂在指定年月的每日檔期狀態。
    導入 ADR-v3-01 預產期 7 天緩衝鎖定與服務中解鎖機制。
    回傳字典: { date_day(int): { 'status': 'white'/'yellow'/'red', 'client_name': '...', 'case_no': ..., 'is_work_day': bool } }
    """
    from datetime import date, datetime, timedelta
    conn = get_connection()
    schedule_map = {}
    
    def parse_dt(val):
        if not val:
            return None
        if isinstance(val, datetime):
            return val.date()
        if hasattr(val, "date"):
            return val
        if isinstance(val, (str, bytes)):
            try:
                return datetime.strptime(str(val).split(" ")[0].strip(), "%Y-%m-%d").date()
            except:
                return None
        return val

    try:
        with conn.cursor() as cursor:
            # 1. 讀取月嫂所有有效訂單 (洽談中/訂單成立/服務中/訂單完成) 進行動態天數與緩衝期計算
            cursor.execute("""
                SELECT o.case_no, o.status AS order_status, o.start_date, o.end_date,
                       o.actual_start_date, o.service_days, c.name AS client_name
                FROM orders o
                JOIN clients c ON o.client_id = c.id
                WHERE o.staff_id = %s AND o.status != '訂單取消'
            """, (staff_id,))
            orders = cursor.fetchall()
            
            for o in orders:
                st_date = parse_dt(o['actual_start_date']) or parse_dt(o['start_date'])
                if not st_date:
                    continue
                days_cnt = o['service_days'] or 20
                ed_date = st_date + timedelta(days=days_cnt - 1)
                
                status = o['order_status']
                
                # 計算該訂單影響的日期區間
                # 洽談中/訂單成立：服務期間 + 結束後 7 天 (黃底鎖定)
                # 服務中/訂單完成：服務期間 (紅底)，後續 7 天自動解鎖
                main_color = 'red' if status in ['服務中', '訂單完成'] else 'yellow'
                
                # A. 服務期間區間
                curr = st_date
                while curr <= ed_date:
                    if curr.year == year and curr.month == month:
                        schedule_map[curr.day] = {
                            'status': main_color,
                            'client_name': o['client_name'],
                            'case_no': o['case_no'],
                            'is_work_day': True,
                            'is_double_pay': False
                        }
                    curr += timedelta(days=1)
                    
                # B. 預排階段 (洽談中/訂單成立) 額外計算結束後 7 天緩衝鎖定 (黃底)
                if status in ['洽談中', '訂單成立']:
                    buffer_start = ed_date + timedelta(days=1)
                    buffer_end = ed_date + timedelta(days=7)
                    curr = buffer_start
                    while curr <= buffer_end:
                        if curr.year == year and curr.month == month:
                            # 若當天尚未被其他權重更高的排班設定，寫入緩衝鎖定
                            if curr.day not in schedule_map:
                                schedule_map[curr.day] = {
                                    'status': 'yellow',
                                    'client_name': f"{o['client_name']} (預留備用期)",
                                    'case_no': o['case_no'],
                                    'is_work_day': False,
                                    'is_double_pay': False
                                }
                        curr += timedelta(days=1)
                        
            # 2. 疊加 staff_schedule 明細對特定日期個體設定進行覆蓋
            cursor.execute("""
                SELECT s.*, c.name AS client_name, o.status AS order_status, o.custom_rest_dates
                FROM staff_schedule s
                JOIN orders o ON s.case_no = o.case_no
                JOIN clients c ON o.client_id = c.id
                WHERE s.staff_id = %s AND YEAR(s.work_date) = %s AND MONTH(s.work_date) = %s
            """, (staff_id, year, month))
            rows = cursor.fetchall()
            
            today_date = date.today()
            for r in rows:
                w_date = parse_dt(r['work_date'])
                if not w_date:
                    continue
                day = w_date.day
                
                # 判斷是否為排定休假 (is_work_day == False 標示為綠底 🟢)
                if r['order_status'] == '訂單取消':
                    status = 'white'
                elif not r['is_work_day']:
                    status = 'green'  # 🟢 綠底休假/請假
                elif w_date <= today_date or r['order_status'] in ['服務中', '訂單完成']:
                    status = 'red'
                else:
                    status = 'yellow'
                
                schedule_map[day] = {
                    'status': status,
                    'client_name': r['client_name'],
                    'case_no': r['case_no'],
                    'is_work_day': bool(r['is_work_day']),
                    'is_double_pay': bool(r['is_double_pay']),
                    'schedule_id': r['id']
                }
            return schedule_map
    finally:
        conn.close()

def get_order_matches(case_no: str) -> list[dict]:
    """獲取特定訂單的所有媒合意願記錄與發送狀態"""
    case_no = _resolve_case_no(case_no)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT m.*, s.name AS staff_name, s.phone AS staff_phone
                FROM matching_records m
                JOIN staff s ON m.staff_id = s.id
                WHERE m.case_no = %s
                ORDER BY m.sent_at DESC
            """, (case_no,))
            return cursor.fetchall()
    finally:
        conn.close()

def calculate_attendance_schedule(
    actual_start_date, 
    target_service_days: int, 
    service_mode: str = '週休1日', 
    custom_rest_weekdays: list = None,
    custom_leave_dates: set = None,
    custom_work_dates: set = None,
    custom_holiday_rest_dates: set = None,
    monthly_salary_base: float = 0.0
) -> dict:
    """
    出勤天數精算核心算法 (ADR-v4-01, ADR-v4-02, ADR-v5-01, ADR-v6-01 & ADR-v7-01):
    根據確定開始日、目標服務天數 N、單日動態請假與國定假日單日自主出勤勾選集合，
    自動順延計算最終完工日、個體國定假日出勤狀態與週報拆解統計。
    """
    from datetime import datetime, timedelta
    
    def parse_d(val):
        if not val:
            return None
        if isinstance(val, datetime):
            return val.date()
        if hasattr(val, "date"):
            return val
        if isinstance(val, (str, bytes)):
            try:
                return datetime.strptime(str(val).split(" ")[0].strip(), "%Y-%m-%d").date()
            except:
                return None
        return val

    st_d = parse_d(actual_start_date)
    if not st_d:
        return {}
        
    N = int(target_service_days or 20)
    
    leave_dates = set(custom_leave_dates) if custom_leave_dates is not None else set()
    work_dates = set(custom_work_dates) if custom_work_dates is not None else set()
    
    # 讀取國定假日對照表
    conn = get_connection()
    holiday_map = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT holiday_date, holiday_name FROM holidays")
            for h in cursor.fetchall():
                hd = parse_d(h['holiday_date'])
                if hd:
                    holiday_map[hd] = h['holiday_name']
    finally:
        conn.close()

    # 若未自訂國定假日放假集合，預設所有國定假日全放假 (休假順延 1 天)
    if custom_holiday_rest_dates is None:
        holiday_rest_dates = set(holiday_map.keys())
    else:
        holiday_rest_dates = set(custom_holiday_rest_dates)

    # 判定每週預設排休星期的集合 (ADR-v18-04)
    if custom_rest_weekdays is not None:
        rest_weekdays = set(custom_rest_weekdays)
    else:
        if service_mode == '週休1日':
            rest_weekdays = {6}       # 預設週日 (Sunday == 6)
        elif service_mode == '週休2日':
            rest_weekdays = {5, 6}    # 預設週六、週日 (Saturday == 5, Sunday == 6)
        else:
            rest_weekdays = set()

    # 迴圈計算出勤天數直至滿 N 個工作日
    curr = st_d
    worked_days_count = 0
    day_by_day = []
    national_holidays_found = []
    
    while worked_days_count < N:
        is_holiday = curr in holiday_map
        h_name = holiday_map.get(curr, None)
        
        # 判定今天是否為休假/請假:
        # 1. 符合每週預設排休 (例如週休二日之六日)
        # 2. 或單日排休選單點選 (leave_dates)
        # 3. 或國定假日選單勾選放假
        is_weekday_rest = curr.weekday() in rest_weekdays and curr not in work_dates
        
        if is_holiday:
            is_rest = is_weekday_rest or (curr in leave_dates) or (curr in holiday_rest_dates)
            national_holidays_found.append({
                'date': curr, 
                'name': h_name, 
                'is_worked': not is_rest
            })
        else:
            is_rest = is_weekday_rest or (curr in leave_dates)

        if not is_rest:
            worked_days_count += 1
            is_work = True
        else:
            is_work = False
            
        day_by_day.append({
            'date': curr,
            'day_num': len(day_by_day) + 1,
            'is_work_day': is_work,
            'is_rest_day': is_rest,
            'holiday_name': h_name
        })
        
        if worked_days_count < N:
            curr += timedelta(days=1)

    actual_end_date = curr
    total_calendar_days = len(day_by_day)
    rest_days_count = total_calendar_days - N
    
    total_estimated_salary = monthly_salary_base
    
    # 週報拆解統計 (每 7 天為 1 週)
    weekly_stats = []
    for i in range(0, total_calendar_days, 7):
        chunk = day_by_day[i:i+7]
        w_idx = i // 7 + 1
        w_work = sum(1 for d in chunk if d['is_work_day'])
        w_rest = sum(1 for d in chunk if d['is_rest_day'])
        w_holidays = sum(1 for d in chunk if d['holiday_name'])
        weekly_stats.append({
            'week_num': w_idx,
            'start_date': chunk[0]['date'],
            'end_date': chunk[-1]['date'],
            'work_days': w_work,
            'rest_days': w_rest,
            'holiday_days': w_holidays
        })

    return {
        'actual_start_date': st_d,
        'actual_end_date': actual_end_date,
        'target_service_days': N,
        'total_calendar_days': total_calendar_days,
        'actual_work_days_count': N,
        'rest_days_count': rest_days_count,
        'national_holidays_found': national_holidays_found,
        'total_estimated_salary': total_estimated_salary,
        'weekly_stats': weekly_stats,
        'day_by_day': day_by_day
    }

def parse_client_district(city: str, address: str) -> str:
    """ponytail: extract administrative district from client city and address"""
    full_str = f"{city or ''} {address or ''}"
    districts = ["香山區", "東區", "北區", "竹北市", "竹東鎮", "新埔鎮", "關西鎮", "湖口鄉", "新豐鄉", "芎林鄉", "橫山鄉", "北埔鄉", "寶山鄉", "峨眉鄉", "尖石鄉", "五峰鄉", "頭份市", "竹南鎮"]
    for d in districts:
        if d in full_str:
            return d
    if city:
        return city
    return ""

def get_recommended_staff_for_order(
    case_no: str,
    filter_region: bool = True,
    filter_schedule: bool = True,
    filter_babies: bool = True,
    filter_time: bool = True
) -> list[dict]:
    """
    智慧粗篩比對月嫂推薦引擎，支援 7 天預留備用期持久化掃描與 city/address 區域比對。
    """
    case_no = _resolve_case_no(case_no)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.case_no, o.start_date, o.end_date, o.actual_start_date, o.service_days, o.service_hours_per_day,
                       c.id AS client_id, c.name AS client_name, c.city, c.address, c.baby_info, c.service_time
                FROM orders o
                JOIN clients c ON o.client_id = c.id
                WHERE o.case_no = %s
            """, (case_no,))
            order_info = cursor.fetchone()
            if not order_info:
                return []

            o_st = order_info.get('actual_start_date') or order_info.get('start_date')
            o_ed = order_info.get('end_date')
            client_district = parse_client_district(order_info.get('city'), order_info.get('address'))
            client_baby = str(order_info.get('baby_info') or '')
            is_twins = "雙胞胎" in client_baby or "2" in client_baby

            cursor.execute("SELECT * FROM staff WHERE status = 'active'")
            staff_list = cursor.fetchall()

            cursor.execute("SELECT staff_id, region_name FROM staff_regions")
            region_rows = cursor.fetchall()
            staff_region_map = {}
            for r in region_rows:
                sid = r['staff_id']
                staff_region_map.setdefault(sid, set()).add(r['region_name'])

            cursor.execute("""
                SELECT case_no, staff_id, start_date, end_date, actual_start_date
                FROM orders 
                WHERE staff_id IS NOT NULL AND status NOT IN ('訂單取消') AND case_no != %s
            """, (case_no,))
            existing_orders = cursor.fetchall()

            recommendations = []

            for s in staff_list:
                sid = s['id']
                reasons = []
                reject_reasons = []
                score = 100

                # 1. 服務區域比對
                s_regions = staff_region_map.get(sid, set())
                if s.get('service_regions'):
                    try:
                        import json
                        sr_list = json.loads(s['service_regions']) if isinstance(s['service_regions'], str) else s['service_regions']
                        s_regions.update(sr_list)
                    except:
                        pass

                region_matched = True
                if client_district and s_regions:
                    if not any(client_district in r or r in client_district for r in s_regions):
                        region_matched = False
                        reject_reasons.append(f"區域不符 ({client_district})")
                        score -= 40
                    else:
                        reasons.append(f"符合區域 ({client_district})")
                else:
                    reasons.append("區域可承接")

                # 2. 檔期衝突掃描 (包含 7 天預留備用期持久化計算)
                schedule_conflict = False
                if o_st:
                    o_end_date = o_ed or (o_st + timedelta(days=safe_int(order_info.get('service_days', 20))))
                    for eo in existing_orders:
                        if eo['staff_id'] == sid:
                            eo_st = eo.get('actual_start_date') or eo.get('start_date')
                            eo_ed = eo.get('end_date') or (eo_st + timedelta(days=20)) if eo_st else None
                            if eo_st and eo_ed:
                                # 包含 7 天預留備用期！
                                eo_buffered_end = eo_ed + timedelta(days=7)
                                if (o_st <= eo_buffered_end) and (o_end_date >= eo_st):
                                    schedule_conflict = True
                                    reject_reasons.append(f"檔期衝突(含7天備用期至{eo_buffered_end.strftime('%m/%d')})")
                                    score -= 50
                                    break
                if not schedule_conflict:
                    reasons.append("檔期無衝突")

                # 3. 照顧胎數比對
                care_babies = safe_int(s.get('care_babies', 1))
                if is_twins and care_babies < 2:
                    reject_reasons.append("不承接雙胞胎")
                    score -= 30
                else:
                    reasons.append("胎數符合")

                # 4. 可選條件過濾執行
                is_eligible = True
                if filter_region and not region_matched:
                    is_eligible = False
                if filter_schedule and schedule_conflict:
                    is_eligible = False
                if filter_babies and is_twins and care_babies < 2:
                    is_eligible = False

                if is_eligible:
                    status_prefix = "🟢 100% 匹配" if score >= 90 else ("🟡 部分匹配" if score >= 60 else "⚠️ 條件較不符")
                    reason_str = " | ".join(reasons)
                    if reject_reasons:
                        reason_str += f" (警示: {', '.join(reject_reasons)})"
                    
                    display_label = f"{s['name']} ({s.get('phone', '')}) - {status_prefix} [{reason_str}]"
                    
                    recommendations.append({
                        'staff_id': sid,
                        'name': s['name'],
                        'phone': s.get('phone'),
                        'line_user_id': s.get('line_user_id'),
                        'score': score,
                        'display_label': display_label,
                        'is_perfect': score >= 90,
                        'reasons': reasons,
                        'reject_reasons': reject_reasons
                    })

            recommendations.sort(key=lambda x: x['score'], reverse=True)
            return recommendations
    finally:
        conn.close()

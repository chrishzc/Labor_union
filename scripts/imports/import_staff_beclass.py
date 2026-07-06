# -*- coding: utf-8 -*-
"""
File: scripts/imports/import_staff_beclass.py
Description: \u89e3\u6790\u4e26\u6e05\u6d17\u670d\u52d9\u4eba\u54e1 BeClass \u5831\u540d\u540d\u518a Excel\uff0c\u4ee5\u300c\u8eab\u5206\u8b49\u5b57\u865f\u300d\u70ba\u552f\u4e00\u9375\u53bb\u91cd\u66f4\u65b0\u5beb\u5165 staff \u4e3b\u8868\u8207 7 \u5f35\u5b50\u8868\u3002
ponytail: \u5b50\u8868\u63a1\u7528 Delete-and-Insert \u7b56\u7565\uff0c\u7c21\u55ae\u7c97\u66b4\u4f46\u5c0d\u5c0f\u91cf\u8cc7\u6599\u6700\u6709\u6548\u3002\u8d85\u904e\u5343\u7b46\u518d\u8003\u616e batch upsert\u3002
"""
import sys
import os
import re
import pymysql
import pandas as pd
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '1234',
    'database': 'union_db',
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

def import_checkbox_options(cursor, staff_id, row, options_list, target_table, value_col, detail_col=None, excel_detail_col=None):
    """\u8907\u9078\u6846\u6b04\u4f4d\u7684\u901a\u7528\u532f\u5165\u51fd\u5f0f\uff0c\u63a1\u7528 Delete-and-Insert \u7b56\u7565\u3002"""
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
                (staff_id, '\u5176\u4ed6', str(other_val).strip())
            )

def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"\u932f\u8aa4\uff1a\u627e\u4e0d\u5230 Excel \u6a94\u6848\uff1a{excel_path}")
        return 0, 0

    print(f"\u89e3\u6790 Excel \u6a94\u6848\uff1a{excel_path} ...")
    xl = pd.ExcelFile(excel_path)

    # \u5c0b\u627e\u5305\u542b '\u670d\u52d9\u4eba\u54e1' \u6216 'staff' \u7684\u5206\u9801
    target_sheet = None
    for name in xl.sheet_names:
        clean_name = name.replace(" ", "").lower()
        if '\u670d\u52d9\u4eba\u54e1' in name or 'staff' in clean_name:
            target_sheet = name
            break

    if not target_sheet:
        print("\u672a\u627e\u5230\u5305\u542b '\u670d\u52d9\u4eba\u54e1' \u95dc\u9375\u5b57\u7684\u5de5\u4f5c\u8868\u3002\u8df3\u904e\u6b64\u6a94\u6848\u3002")
        return 0, 0

    df = xl.parse(target_sheet)
    print(f"\u627e\u5230\u5339\u914d\u5de5\u4f5c\u8868\uff1a'{target_sheet}'\uff0c\u5171\u6709 {len(df)} \u7b46\u8cc7\u6599\uff0c\u6e96\u5099\u532f\u5165...")

    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SET NAMES utf8mb4;")
        conn.commit()
    except Exception as e:
        print(f"\u8cc7\u6599\u5eab\u9023\u7dda\u5931\u6557\uff1a{e}")
        return 0, 0

    inserted = 0
    updated = 0

    try:
        for _, row in df.iterrows():
            name = clean_data(row.get('\u59d3\u540d'), 'name')
            if not name:
                continue

            identity_card = clean_data(row.get('\u8eab\u5206\u8b49\u5b57\u865f'), 'identity_card')
            ip_address = clean_data(row.get('IP\u4f4d\u5740'), 'ip_address')

            if not identity_card:
                continue

            # \u6e05\u6d17\u5831\u540d\u6642\u9593
            registered_at = None
            reg_val = row.get('\u5831\u540d\u6642\u9593')
            if pd.notna(reg_val):
                try:
                    registered_at = pd.to_datetime(reg_val).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    registered_at = str(reg_val).strip()

            # \u6e05\u6d17\u751f\u65e5
            birthday = None
            b_date_val = row.get('\u6c11\u570b\u51fa\u751f\u5e74\u6708\u65e5')
            if pd.notna(b_date_val):
                try:
                    if isinstance(b_date_val, (datetime, pd.Timestamp)):
                        birthday = b_date_val.strftime("%Y-%m-%d")
                    else:
                        birthday = str(b_date_val).strip()[:10]
                except Exception:
                    pass
            if not birthday:
                birthday = clean_birth_date(row.get('\u51fa\u751f\u5e74'), row.get('\u6708'), row.get('\u65e5'))

            city, address = clean_city_and_address(row.get('\u7e23\u5e02'), row.get('\u5730\u5740'))
            phone = clean_phone(row.get('\u884c\u52d5\u96fb\u8a71'))

            has_massage_cert = False
            massage_val = row.get('有嬰幼兒按摩證書嗎?')
            if pd.notna(massage_val) and str(massage_val).strip() in ['有', 'Y', 'y', '1', 'True', 'true']:
                has_massage_cert = True

            # 解析可承接胎數 (care_babies: 1:單胞胎, 2:雙胞胎, 3:三胞胎)
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

            # 以身分證字號為唯一鍵去重
            cursor.execute("SELECT id FROM staff WHERE identity_card = %s", (identity_card,))
            existing = cursor.fetchone()

            if existing:
                staff_id = existing[0]
                update_cols = []
                val_list = []
                for k, v in record.items():
                    # ponytail: \u6392\u9664\u5c0d line_user_id \u7684\u8986\u5beb
                    if k not in ['identity_card', 'line_user_id']:
                        update_cols.append(f"`{k}` = %s")
                        val_list.append(v)
                val_list.append(identity_card)
                sql = f"UPDATE staff SET {', '.join(update_cols)} WHERE identity_card = %s"
                cursor.execute(sql, tuple(val_list))
                updated += 1
            else:
                cols = ", ".join([f"`{k}`" for k in record.keys()])
                places = ", ".join(["%s"] * len(record))
                sql = f"INSERT INTO staff ({cols}) VALUES ({places})"
                cursor.execute(sql, tuple(record.values()))
                staff_id = cursor.lastrowid
                inserted += 1

            # === \u5b50\u8868\u66f4\u65b0 (Delete-and-Insert) ===

            # 1. \u9280\u884c\u5e33\u6236
            cursor.execute("DELETE FROM staff_bank_accounts WHERE staff_id = %s", (staff_id,))
            bank_acc = clean_data(row.get('\u9280\u884c\u5e33\u865f'), 'account_no')
            if bank_acc:
                bank_branch = clean_data(row.get('\u9280\u884c\u4ee33\u78bc+\u5206\u884c\u4ee3\u865f4\u78bc'), 'bank_branch')
                bank_code = bank_branch[:3] if bank_branch and len(bank_branch) >= 3 else None
                branch_code = bank_branch[3:] if bank_branch and len(bank_branch) > 3 else None
                cursor.execute(
                    "INSERT INTO staff_bank_accounts (staff_id, bank_code, branch_code, account_no, is_primary) VALUES (%s, %s, %s, %s, %s)",
                    (staff_id, bank_code, branch_code, bank_acc, True)
                )
                add_acc = row.get('\u82e5\u6709\u5176\u5b83\u540c\u9280\u884c\u5e33\u865f\uff0c\u8acb\u4e00\u4f75\u63d0\u4f9b\u3002(\u6c38\u8c50\u6216\u53f0\u65b0)')
                if pd.notna(add_acc) and str(add_acc).strip():
                    acc_clean = re.sub(r'\D', '', str(add_acc))
                    if len(acc_clean) >= 8:
                        cursor.execute(
                            "INSERT INTO staff_bank_accounts (staff_id, bank_code, branch_code, account_no, is_primary) VALUES (%s, %s, %s, %s, %s)",
                            (staff_id, None, None, acc_clean, False)
                        )

            # 2. \u53ef\u627f\u63a5\u5340\u57df
            import_checkbox_options(cursor, staff_id, row,
                options_list=['\u5317\u5340', '\u6771\u5340', '\u9999\u5c71\u5340', '\u65b0\u7af9\u7e23', '\u82d7\u6817\u7e23'],
                target_table='staff_regions', value_col='region_name',
                detail_col='custom_region_detail', excel_detail_col='[\u5176\u5b83].1')

            # 3. \u53ef\u627f\u63a5\u6642\u6bb5
            import_checkbox_options(cursor, staff_id, row,
                options_list=['4\u5c0f\u6642(\u4e0a\u53488:30-12:30)', '4\u5c0f\u6642(\u4e0b\u534813:00-17:00)', '8\u5c0f\u6642', '24\u5c0f\u6642'],
                target_table='staff_time_slots', value_col='slot_name',
                detail_col='custom_slot_detail', excel_detail_col='[\u5176\u5b83].2')

            # 4. \u6708\u5b50\u9910\u9ede\u6599\u7406
            import_checkbox_options(cursor, staff_id, row,
                options_list=['\u8477\u98df', '\u7d20\u98df'],
                target_table='staff_cooking_skills', value_col='skill_name',
                detail_col='custom_skill_detail', excel_detail_col='[\u5176\u5b83]')

            # 5. \u4ea4\u901a\u5de5\u5177
            import_checkbox_options(cursor, staff_id, row,
                options_list=['\u6a5f\u8eca', '\u8f4e\u8eca'],
                target_table='staff_transportation', value_col='vehicle_type')

            # 6. \u7bc0\u65e5\u4e0a\u73ed\u610f\u9858
            import_checkbox_options(cursor, staff_id, row,
                options_list=['\u5e74\u7bc0\u8fb2\u66c6\u904e\u5e74\u521d\u4e00', '\u5e74\u7bc0\u8fb2\u66c6\u904e\u5e74\u521d\u4e8c', '\u5e74\u7bc0\u8fb2\u66c6\u904e\u5e74\u521d\u4e09', '\u7aef\u5348\u7bc0', '\u4e2d\u79cb\u7bc0', '\u570b\u5b9a\u5047\u65e5\u5fc5\u4f11'],
                target_table='staff_holiday_availability', value_col='holiday_name',
                detail_col='custom_holiday_detail', excel_detail_col='[\u5176\u5b83].5')

            # 7. \u9031\u4f11\u504f\u597d
            import_checkbox_options(cursor, staff_id, row,
                options_list=['\u9023\u7e8c\u670d\u52d9', '\u9031\u4f111\u65e5', '\u9031\u4f112\u65e5'],
                target_table='staff_weekly_rest', value_col='rest_type',
                detail_col='custom_rest_detail', excel_detail_col='[\u5176\u5b83].3')

            # 8. \u53ef\u627f\u63a5\u80ce\u6578
            import_checkbox_options(cursor, staff_id, row,
                options_list=['\u55ae\u80de\u80ce', '\u96d9\u80de\u80ce'],
                target_table='staff_baby_types', value_col='baby_type',
                detail_col='custom_baby_detail', excel_detail_col='[\u5176\u5b83].4')

        conn.commit()
        print(f"\u532f\u5165\u6210\u529f\uff1a\u65b0\u589e {inserted} \u7b46\u670d\u52d9\u4eba\u54e1\u8cc7\u6599\uff0c\u66f4\u65b0 {updated} \u7b46\u670d\u52d9\u4eba\u54e1\u8cc7\u6599\u3002")
    except Exception as err:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"\u57f7\u884c\u51fa\u932f\u5df2 Rollback\uff1a{err}")
    finally:
        conn.close()

    return inserted, updated

if __name__ == "__main__":
    excel_arg = sys.argv[1] if len(sys.argv) > 1 else "document/\u8cc7\u6599\u5eab\u3001\u8cc7\u6599\u8655\u7406/\u5047\u8cc7\u6599_\u7bc4\u4f8b.xlsx"
    process_import(excel_arg)

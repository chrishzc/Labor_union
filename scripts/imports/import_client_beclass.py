# -*- coding: utf-8 -*-
"""
File: scripts/imports/import_client_beclass.py
Description: \u89e3\u6790\u4e26\u6e05\u6d17\u5ba2\u6236 BeClass \u5831\u540d\u540d\u518a Excel\uff0c\u4ee5\u300c\u59d3\u540d+\u51fa\u751f\u5e74\u6708\u65e5\u300d\u7d44\u5408\u552f\u4e00\u9375\u53bb\u91cd\u66f4\u65b0\u5beb\u5165 beclass_records \u8cc7\u6599\u8868\u3002
ponytail: 60+ \u500b\u554f\u5377\u6b04\u4f4d\u6253\u5305\u70ba JSON\uff0c\u907f\u514d\u70ba\u6bcf\u500b\u554f\u984c\u5efa\u6b04\u3002
"""
import sys
import os
import re
import json
import pymysql
import pandas as pd

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

# BeClass \u6838\u5fc3\u6b04\u4f4d\u5c0d\u7167 (\u5176\u9918\u554f\u5377\u6b04\u4f4d\u6253\u5305\u9032 survey_details JSON)
BECLASS_CORE_MAPPING = {
    '\u9805\u6b21': 'seq_num',
    '\u67e5\u8a62\u5e8f\u865f': 'query_no',
    '\u5831\u540d\u6642\u9593': 'created_at',
    '\u8a02\u55ae\u7de8\u865f': 'order_no',
    '\u59d3\u540d': 'name',
    '\u6027\u5225': 'gender',
    'Email': 'email',
    '\u884c\u52d5\u96fb\u8a71': 'phone',
    '\u5e02\u8a71': 'tel',
    '\u5206\u6a5f': 'ext',
    '\u7e23\u5e02': 'city',
    '\u90f5\u905e\u5340\u865f': 'zip_code',
    '\u5730\u5740': 'address',
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

def process_import(excel_path):
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到 Excel 檔案：{excel_path}")
        return 0, 0

    print(f"解析 Excel 檔案：{excel_path} ...")
    xl = pd.ExcelFile(excel_path)

    # ponytail: 確定每份檔案只有單一分頁，直接讀取第一個分頁，不進行名稱篩選
    if not xl.sheet_names:
        print("工作表為空。跳過此檔案。")
        return 0, 0
    target_sheet = xl.sheet_names[0]

    df = xl.parse(target_sheet)
    print(f"找到匹配工作表：'{target_sheet}'，共有 {len(df)} 筆資料，準備匯入...")

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

            name = record.get('name')
            birth_date = record.get('birth_date')

            # \u7d44\u5408\u552f\u4e00\u9375\uff1a\u59d3\u540d + \u51fa\u751f\u5e74\u6708\u65e5\uff0c\u5169\u8005\u7f3a\u4e00\u4e0d\u53ef
            if not name or not birth_date:
                continue

            # \u5c07\u554f\u5377\u7d30\u9805 dict \u8f49\u70ba JSON
            record['survey_details'] = json.dumps(details, ensure_ascii=False)

            # \u4ee5\u300c\u59d3\u540d + \u51fa\u751f\u5e74\u6708\u65e5\u300d\u7d44\u5408\u9375\u6bd4\u5c0d\u53bb\u91cd
            cursor.execute(
                "SELECT id FROM beclass_records WHERE name = %s AND birth_date = %s",
                (name, birth_date)
            )
            existing = cursor.fetchone()

            if existing:
                update_cols = []
                val_list = []
                for k, v in record.items():
                    if k not in ['name', 'birth_date']:
                        update_cols.append(f"`{k}` = %s")
                        val_list.append(v)
                val_list.extend([name, birth_date])
                sql = f"UPDATE beclass_records SET {', '.join(update_cols)} WHERE name = %s AND birth_date = %s"
                cursor.execute(sql, tuple(val_list))
                updated += 1
            else:
                cols = ", ".join([f"`{k}`" for k in record.keys()])
                places = ", ".join(["%s"] * len(record))
                sql = f"INSERT INTO beclass_records ({cols}) VALUES ({places})"
                cursor.execute(sql, tuple(record.values()))
                inserted += 1

        conn.commit()
        print(f"\u532f\u5165\u6210\u529f\uff1a\u65b0\u589e {inserted} \u7b46\u5ba2\u6236 BeClass \u8cc7\u6599\uff0c\u66f4\u65b0 {updated} \u7b46\u5ba2\u6236 BeClass \u8cc7\u6599\u3002")
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

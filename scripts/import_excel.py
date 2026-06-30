import sys
import os
import json
import re
import pymysql
import pandas as pd

# 確保中文輸出編碼正確
sys.stdout.reconfigure(encoding='utf-8')

# 資料庫連線配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '1234',
    'database': 'union_db',
    'charset': 'utf8mb4'
}

# 1. clients 欄位映射關係
CLIENTS_FIELD_MAPPING = {
    '項次': 'seq_num',
    '案件狀態': 'status',
    '不符合原因': 'reject_reason',
    '查詢序號(案件編號)': 'case_no',
    '報名時間(建檔)': 'created_at',
    'IP位址': 'ip_address',
    '姓名': 'name',
    '性別': 'gender',
    '行動電話': 'phone',
    '縣市': 'city',
    '地址': 'address',
    '身分資格': 'identity_status',
    '服務時間': 'service_time',
    '預產期/預計服務開始月份': 'due_month',
    '預計服務日期': 'service_start_date',
    '其他事項': 'notes',
    '希望服務天數': 'service_days',
    '居住型態': 'residence_type',
    '生產方式': 'delivery_type',
    '服務方式': 'service_type',
    '寶寶資訊': 'baby_info',
    'LINE ID': 'line_id',
    '管理者註記事項': 'admin_notes'
}

# 2. beclass 欄位映射關係
BECLASS_CORE_MAPPING = {
    '項次': 'seq_num',
    '查詢序號': 'query_no',
    '報名時間': 'created_at',
    '訂單編號': 'order_no',
    '姓名': 'name',
    '性別': 'gender',
    'Email': 'email',
    '行動電話': 'phone',
    '市話': 'tel',
    '分機': 'ext',
    '縣市': 'city',
    '郵遞區號': 'zip_code',
    '地址': 'address',
    '管理者註記事項': 'admin_notes'
}

def clean_phone(phone_val):
    if pd.isna(phone_val) or not phone_val:
        return None
    # 轉為字串並去除所有空格與破折號
    phone = str(phone_val).replace(" ", "").replace("-", "").strip()
    # 移除非數字字元 (保留開頭的 +)
    phone = re.sub(r'(?<!^)\D', '', phone)
    
    # 處理國碼 +8869... 轉為 09...
    if phone.startswith("+886"):
        phone = "0" + phone[4:]
    elif phone.startswith("886"):
        phone = "0" + phone[3:]
        
    # 處理 Excel 漏掉開頭 0 的情況 (例如 9開頭且長度為 9 碼的手機)
    if len(phone) == 9 and phone.startswith("9"):
        phone = "0" + phone
        
    return phone

def clean_city_and_address(city_val, address_val):
    city = str(city_val).strip() if pd.notna(city_val) else ""
    address = str(address_val).strip() if pd.notna(address_val) else ""
    
    # 統一「台」與「臺」
    city = city.replace("臺", "台")
    address = address.replace("臺", "台")
    
    # 自動補全：如果縣市為空，從地址中提取前 3 個字
    if not city and len(address) >= 3:
        for possible_city in ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣"]:
            if address.startswith(possible_city):
                city = possible_city
                break
    
    # 修正只寫「台北」或「台中」的狀況
    if city in ["台北", "新北", "桃園", "台中", "台南", "高雄"]:
        city = city + "市"
    elif city in ["新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭", "花蓮", "台東", "澎湖"]:
        city = city + "縣"
        
    return city, address

def clean_birth_date(year_val, month_val, day_val):
    if pd.isna(year_val) or pd.isna(month_val) or pd.isna(day_val):
        return None
    try:
        y = int(year_val)
        m = int(month_val)
        d = int(day_val)
        
        # 民國年轉西元年
        if y < 1900:
            y += 1911
            
        # 驗證日期合法性
        import datetime
        valid_date = datetime.date(y, m, d)
        return valid_date.strftime("%Y-%m-%d")
    except:
        return None

def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name in ['seq_num', 'service_days']:
        try:
            return int(val)
        except:
            return None
    return str(val).strip()

def import_clients_sheet(cursor, df):
    print("-> 正在將 'HCM 月子平台 -市府' 匯入 clients 表...")
    inserted = 0
    updated = 0
    
    for index, row in df.iterrows():
        record = {}
        for excel_col, db_col in CLIENTS_FIELD_MAPPING.items():
            if excel_col in row:
                record[db_col] = clean_data(row[excel_col], db_col)
        
        # 資料清洗與校正
        if 'phone' in record:
            record['phone'] = clean_phone(record['phone'])
        
        # 清洗地址與縣市
        if 'city' in record or 'address' in record:
            clean_c, clean_a = clean_city_and_address(record.get('city'), record.get('address'))
            record['city'] = clean_c
            record['address'] = clean_a
            
        if not record.get('case_no'):
            continue

        # 比對去重
        cursor.execute("SELECT id FROM clients WHERE case_no = %s", (record['case_no'],))
        existing = cursor.fetchone()

        if existing:
            update_cols = []
            val_list = []
            for k, v in record.items():
                if k != 'case_no':
                    update_cols.append(f"`{k}` = %s")
                    val_list.append(v)
            val_list.append(record['case_no'])
            sql = f"UPDATE clients SET {', '.join(update_cols)} WHERE case_no = %s"
            cursor.execute(sql, tuple(val_list))
            updated += 1
        else:
            cols = ", ".join([f"`{k}`" for k in record.keys()])
            places = ", ".join(["%s"] * len(record))
            sql = f"INSERT INTO clients ({cols}) VALUES ({places})"
            cursor.execute(sql, tuple(record.values()))
            inserted += 1
            
    print(f"   clients 表匯入完成：新增 {inserted} 筆，更新 {updated} 筆。")

def import_beclass_sheet(cursor, df):
    print("-> 正在將 'beclass' 匯入 beclass_records 表...")
    inserted = 0
    updated = 0
    
    for index, row in df.iterrows():
        record = {}
        details = {}
        
        for excel_col in df.columns:
            if excel_col in BECLASS_CORE_MAPPING:
                db_col = BECLASS_CORE_MAPPING[excel_col]
                record[db_col] = clean_data(row[excel_col], db_col)
            elif excel_col not in ['出生年', '月', '日', 'Unnamed: 83']: # 過濾空的多餘欄位與生日原始欄位
                # 其餘 60+ 個問卷選項打包進 details JSON
                val = row[excel_col]
                if pd.notna(val):
                    details[excel_col] = str(val).strip()

        # 資料清洗與校正
        if 'phone' in record:
            record['phone'] = clean_phone(record['phone'])
        
        # 清洗地址與縣市
        if 'city' in record or 'address' in record:
            clean_c, clean_a = clean_city_and_address(record.get('city'), record.get('address'))
            record['city'] = clean_c
            record['address'] = clean_a

        # 清洗與合併出生日期
        birth_year = row.get('出生年')
        birth_month = row.get('月')
        birth_day = row.get('日')
        record['birth_date'] = clean_birth_date(birth_year, birth_month, birth_day)

        if not record.get('query_no'):
            continue

        # 將細項 dict 轉為 JSON 字串
        record['survey_details'] = json.dumps(details, ensure_ascii=False)

        # 比對去重
        cursor.execute("SELECT id FROM beclass_records WHERE query_no = %s", (record['query_no'],))
        existing = cursor.fetchone()

        if existing:
            update_cols = []
            val_list = []
            for k, v in record.items():
                if k != 'query_no':
                    update_cols.append(f"`{k}` = %s")
                    val_list.append(v)
            val_list.append(record['query_no'])
            sql = f"UPDATE beclass_records SET {', '.join(update_cols)} WHERE query_no = %s"
            cursor.execute(sql, tuple(val_list))
            updated += 1
        else:
            cols = ", ".join([f"`{k}`" for k in record.keys()])
            places = ", ".join(["%s"] * len(record))
            sql = f"INSERT INTO beclass_records ({cols}) VALUES ({places})"
            cursor.execute(sql, tuple(record.values()))
            inserted += 1
            
    print(f"   beclass_records 表匯入完成：新增 {inserted} 筆，更新 {updated} 筆。")

def import_staff_sheet(cursor, df):
    print("-> 正在將 '服務人員' 匯入 staff 及其關聯屬性表...")
    inserted = 0
    updated = 0
    
    for index, row in df.iterrows():
        # Get basic personal details
        name = clean_data(row.get('姓名'), 'name')
        if not name:
            continue
            
        identity_card = clean_data(row.get('身分證字號'), 'identity_card')
        ip_address = clean_data(row.get('IP位址'), 'ip_address')
        
        # We need a unique identifier. We prefer identity_card. If missing, we use name + ip_address.
        if not identity_card and not ip_address:
            continue
            
        # Clean signup time
        registered_at = None
        reg_val = row.get('報名時間')
        if pd.notna(reg_val):
            try:
                registered_at = pd.to_datetime(reg_val).strftime("%Y-%m-%d %H:%M:%S")
            except:
                registered_at = str(reg_val).strip()
                
        # Clean birthday
        birthday = None
        b_date_val = row.get('民國出生年月日')
        if pd.notna(b_date_val):
            try:
                if isinstance(b_date_val, (datetime, pd.Timestamp)):
                    birthday = b_date_val.strftime("%Y-%m-%d")
                else:
                    birthday = str(b_date_val).strip()[:10]
            except:
                pass
        
        # Fallback to ROC birthday calculation
        if not birthday:
            birthday = clean_birth_date(row.get('出生年'), row.get('月'), row.get('日'))
            
        # Clean address/city
        city, address = clean_city_and_address(row.get('縣市'), row.get('地址'))
        
        # Clean phone
        phone = clean_phone(row.get('行動電話'))
        
        has_massage_cert = False
        massage_val = row.get('有嬰幼兒按摩證書嗎?')
        if pd.notna(massage_val) and str(massage_val).strip() in ['有', 'Y', 'y', '1', 'True', 'true']:
            has_massage_cert = True
            
        # Form staff record dict (removed query_no)
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
            'status': 'active'
        }
        
        # De-duplicate check
        staff_id = None
        if identity_card:
            cursor.execute("SELECT id FROM staff WHERE identity_card = %s", (identity_card,))
            existing = cursor.fetchone()
        else:
            cursor.execute("SELECT id FROM staff WHERE name = %s AND ip_address = %s", (name, ip_address))
            existing = cursor.fetchone()
            
        if existing:
            staff_id = existing[0]
            # Update staff core record
            update_cols = []
            val_list = []
            for k, v in record.items():
                update_cols.append(f"`{k}` = %s")
                val_list.append(v)
            val_list.append(staff_id)
            sql = f"UPDATE staff SET {', '.join(update_cols)} WHERE id = %s"
            cursor.execute(sql, tuple(val_list))
            updated += 1
        else:
            # Insert staff core record
            cols = ", ".join([f"`{k}`" for k in record.keys()])
            places = ", ".join(["%s"] * len(record))
            sql = f"INSERT INTO staff ({cols}) VALUES ({places})"
            cursor.execute(sql, tuple(record.values()))
            staff_id = cursor.lastrowid
            inserted += 1
            
        # Clean and update child tables (Delete-and-Insert strategy)
        
        # 1. Bank Accounts
        cursor.execute("DELETE FROM staff_bank_accounts WHERE staff_id = %s", (staff_id,))
        bank_acc = clean_data(row.get('銀行帳號'), 'account_no')
        if bank_acc:
            bank_branch = clean_data(row.get('銀行代3碼+分行代號4碼'), 'bank_branch')
            bank_code = bank_branch[:3] if bank_branch and len(bank_branch) >= 3 else None
            branch_code = bank_branch[3:] if bank_branch and len(bank_branch) > 3 else None
            cursor.execute(
                "INSERT INTO staff_bank_accounts (staff_id, bank_code, branch_code, account_no, is_primary) VALUES (%s, %s, %s, %s, %s)",
                (staff_id, bank_code, branch_code, bank_acc, True)
            )
            
            # Handle additional accounts
            add_acc = row.get('若有其它同銀行帳號，請一併提供。(永豐或台新)')
            if pd.notna(add_acc) and str(add_acc).strip():
                acc_clean = re.sub(r'\D', '', str(add_acc))
                if len(acc_clean) >= 8:
                    cursor.execute(
                        "INSERT INTO staff_bank_accounts (staff_id, bank_code, branch_code, account_no, is_primary) VALUES (%s, %s, %s, %s, %s)",
                        (staff_id, None, None, acc_clean, False)
                    )
                    
        # Helper for checkbox options
        def import_checkbox_options(options_list, summary_col, target_table, value_col, detail_col=None, excel_detail_col=None):
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
                    
        # 2. Regions
        import_checkbox_options(
            options_list=['北區', '東區', '香山區', '新竹縣', '苗栗縣'],
            summary_col='可承接案件區域',
            target_table='staff_regions',
            value_col='region_name',
            detail_col='custom_region_detail',
            excel_detail_col='[其它].1'
        )
        
        # 3. Time Slots
        import_checkbox_options(
            options_list=['4小時(上午8:30-12:30)', '4小時(下午13:00-17:00)', '8小時', '24小時'],
            summary_col='可承接案件時段',
            target_table='staff_time_slots',
            value_col='slot_name',
            detail_col='custom_slot_detail',
            excel_detail_col='[其它].2'
        )
        
        # 4. Cooking Skills
        import_checkbox_options(
            options_list=['葷食', '素食'],
            summary_col='月子餐點料理',
            target_table='staff_cooking_skills',
            value_col='skill_name',
            detail_col='custom_skill_detail',
            excel_detail_col='[其它]'
        )
        
        # 5. Transportation
        import_checkbox_options(
            options_list=['機車', '轎車'],
            summary_col='服務時交通工具',
            target_table='staff_transportation',
            value_col='vehicle_type'
        )
        
        # 6. Holidays
        import_checkbox_options(
            options_list=['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休'],
            summary_col='特殊節日可上班的部分(計費:服務費雙倍)',
            target_table='staff_holiday_availability',
            value_col='holiday_name',
            detail_col='custom_holiday_detail',
            excel_detail_col='[其它].5'
        )
        
        # 7. Weekly Rest
        import_checkbox_options(
            options_list=['連續服務', '週休1日', '週休2日'],
            summary_col='可服務週間',
            target_table='staff_weekly_rest',
            value_col='rest_type',
            detail_col='custom_rest_detail',
            excel_detail_col='[其它].3'
        )
        
        # 8. Baby Types
        import_checkbox_options(
            options_list=['單胞胎', '雙胞胎'],
            summary_col='可承接的胎數',
            target_table='staff_baby_types',
            value_col='baby_type',
            detail_col='custom_baby_detail',
            excel_detail_col='[其它].4'
        )

    print(f"   staff 及其子表匯入完成：新增 {inserted} 筆，更新 {updated} 筆。")

def main():
    excel_path = '欄位_測試用.xlsx'
    if not os.path.exists(excel_path):
        excel_path = os.path.join(os.path.dirname(__file__), '..', '欄位_測試用.xlsx')
        
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到測試用 Excel 檔案，路徑為：{excel_path}")
        return

    # 連接資料庫
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print("成功連線至 MySQL 資料庫！")
    except Exception as e:
        print(f"資料庫連線失敗：{e}")
        return

    try:
        with connection.cursor() as cursor:
            # 1. 讀取與匯入第一個工作表
            df_clients = pd.read_excel(excel_path, sheet_name='HCM 月子平台 -市府')
            import_clients_sheet(cursor, df_clients)

            # 2. 讀取與匯入第二個工作表
            df_beclass = pd.read_excel(excel_path, sheet_name='beclass')
            import_beclass_sheet(cursor, df_beclass)
            
            # 3. 讀取與匯入服務人員工作表
            df_staff = pd.read_excel(excel_path, sheet_name='服務人員')
            import_staff_sheet(cursor, df_staff)
            
            connection.commit()
            print("\n====== 所有資料分頁匯入成功！ ======")

    except Exception as e:
        connection.rollback()
        print(f"匯入過程中發生錯誤，已進行 Rollback。錯誤原因：{e}")
    finally:
        connection.close()
        print("資料庫連線已關閉。")

if __name__ == "__main__":
    main()

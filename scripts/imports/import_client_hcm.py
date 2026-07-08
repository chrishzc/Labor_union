# -*- coding: utf-8 -*-
"""
File: scripts/imports/import_client_hcm.py
Description: 解析並清洗 HCM 月子平台 -市府 Excel 工作表，將乾淨數據寫入 clients 表，並同步初始化 orders 為「洽談中」。
ponytail: 去重與更新時排除 line_user_id 欄位，自動為新案件在 orders 建立「洽談中」紀錄。
"""
import sys
import os
import re
import pymysql
import pandas as pd

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 資料庫連線配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '1234',
    'database': 'union_db',
    'charset': 'utf8mb4'
}

# 欄位映射關係 (與舊 import_excel.py 一致，但移除 案件狀態 映射以免覆寫 status)
CLIENTS_FIELD_MAPPING = {
    '項次': 'seq_num',
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
    city = city.replace("臺", "台")
    address = address.replace("臺", "台")
    
    if not city and len(address) >= 3:
        for possible_city in ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣"]:
            if address.startswith(possible_city):
                city = possible_city
                break
    
    if city in ["台北", "新北", "桃園", "台中", "台南", "高雄"]:
        city = city + "市"
    elif city in ["新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭", "花蓮", "台東", "澎湖"]:
        city = city + "縣"
        
    return city, address

def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name in ['seq_num', 'service_days']:
        try:
            return int(val)
        except:
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
        # 強制指定 utf8mb4 字元編碼以防止 ENUM 狀態機寫入中文時遭到截斷
        cursor.execute("SET NAMES utf8mb4;")
        conn.commit()
        
        # ponytail: 自動偵測並修復資料庫結構，防止 clients 缺少 status 欄位引發 1054 錯誤
        try:
            cursor.execute("SHOW COLUMNS FROM clients LIKE 'status';")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE clients ADD COLUMN status VARCHAR(50) DEFAULT '洽談中' COMMENT '案件狀態 (符合/不符合)';")
                conn.commit()
                print("[動態修復] clients 資料表缺少 'status' 欄位，已自動新增。")
        except Exception as mig_err:
            pass  # 忽略修復錯誤
            
    except Exception as e:
        print(f"資料庫連線失敗：{e}")
        return 0, 0
        
    inserted = 0
    updated = 0
    
    try:
        for _, row in df.iterrows():
            record = {}
            for excel_col, db_col in CLIENTS_FIELD_MAPPING.items():
                if excel_col in row:
                    record[db_col] = clean_data(row[excel_col], db_col)
            
            # 欄位清理
            if 'phone' in record:
                record['phone'] = clean_phone(record['phone'])
            if 'city' in record or 'address' in record:
                clean_c, clean_a = clean_city_and_address(record.get('city'), record.get('address'))
                record['city'] = clean_c
                record['address'] = clean_a
                
            case_no = record.get('case_no')
            if not case_no:
                continue
                
            # 比對去重
            cursor.execute("SELECT id FROM clients WHERE case_no = %s", (case_no,))
            existing = cursor.fetchone()
            
            if existing:
                client_id = existing[0]
                update_cols = []
                val_list = []
                for k, v in record.items():
                    # ponytail: 排除對 line_user_id 的覆寫，將訂單狀態交給 orders 表生命週期管理
                    if k not in ['case_no', 'line_user_id']:
                        update_cols.append(f"`{k}` = %s")
                        val_list.append(v)
                val_list.append(case_no)
                sql = f"UPDATE clients SET {', '.join(update_cols)} WHERE case_no = %s"
                cursor.execute(sql, tuple(val_list))
                updated += 1
            else:
                cols = ", ".join([f"`{k}`" for k in record.keys()])
                places = ", ".join(["%s"] * len(record))
                sql = f"INSERT INTO clients ({cols}) VALUES ({places})"
                cursor.execute(sql, tuple(record.values()))
                client_id = cursor.lastrowid
                inserted += 1
                
            # 關聯訂單與生命週期狀態機初始化
            # 比對 orders 表是否已有此 client_id (或在此業務下，以 case_no 作為主要核銷欄位)
            cursor.execute("SELECT id FROM orders WHERE client_id = %s", (client_id,))
            order_exists = cursor.fetchone()
            if not order_exists:
                # 取得相關欄位的值以初始化 orders 表中的對應數值
                s_days = clean_data(record.get('service_days'), 'service_days') or 20
                s_time_raw = record.get('service_time') or "9"
                # 清理服務時間時數
                import re
                hrs_match = re.search(r'\d+', str(s_time_raw))
                s_hours = int(hrs_match.group(0)) if hrs_match else 9
                
                # 身分資格轉為對應的 subsidy_eligibility
                sub_elig = "一般市民"
                raw_sub = str(record.get('identity_status') or '')
                if "補助" in raw_sub or "低收" in raw_sub:
                    sub_elig = "補助市民"
                elif "非" in raw_sub:
                    sub_elig = "非市民"

                # 初始化建立 orders，預設 status 為「洽談中」
                cursor.execute("""
                    INSERT INTO orders (client_id, status, service_days, service_hours_per_day, subsidy_eligibility) 
                    VALUES (%s, '洽談中', %s, %s, %s)
                """, (client_id, s_days, s_hours, sub_elig))
                
        conn.commit()
        print(f"匯入成功：新增 {inserted} 筆客戶資料，更新 {updated} 筆客戶資料。")
    except Exception as err:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"執行出錯已 Rollback：{err}")
    finally:
        conn.close()
        
    return inserted, updated

if __name__ == "__main__":
    # 提供預設本機路徑或接收命令列參數
    excel_arg = sys.argv[1] if len(sys.argv) > 1 else "document/資料庫、資料處理/假資料_範例.xlsx"
    process_import(excel_arg)

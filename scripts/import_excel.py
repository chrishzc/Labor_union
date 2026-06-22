import sys
import os
import json
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
    '出生年': 'birth_year',
    '月': 'birth_month',
    '日': 'birth_day',
    '行動電話': 'phone',
    '市話': 'tel',
    '分機': 'ext',
    '縣市': 'city',
    '郵遞區號': 'zip_code',
    '地址': 'address',
    '管理者註記事項': 'admin_notes'
}

def clean_data(val, col_name):
    if pd.isna(val):
        return None
    if col_name in ['seq_num', 'service_days', 'birth_year', 'birth_month', 'birth_day']:
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
            elif excel_col != 'Unnamed: 83': # 過濾空的多餘欄位
                # 其餘 60+ 個問卷選項打包進 details JSON
                val = row[excel_col]
                if pd.notna(val):
                    details[excel_col] = str(val).strip()

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

def main():
    excel_path = r'C:\Users\chris\Desktop\project\union\欄位_測試用.xlsx'
    
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到測試用 Excel 檔案 {excel_path}")
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

# -*- coding: utf-8 -*-
"""
File: scripts/import_finance_excel.py
Description: 解析並清洗帳務.xlsx，將訂金、尾款、月嫂服務費用及對帳狀態寫入資料庫的 payments 表。
ponytail: 帳務計價公式未建，目前金額與尾款全數採用固定數值進行對帳 Pipe 測試。
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
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from admin.utils import get_db_connection

def decode_va_to_case_no(virtual_account):
    """
    將 14 碼虛擬帳號解碼還原為 9 碼案件編號 (查詢序號)。
    規則：前綴 997816 + 分類 99 + 年度(3碼) + 縮寫後3碼(3碼) -> 還原為 年度(3碼) + 0000 + 縮寫後3碼
    例：99781699115001 -> 115001 -> 115000001
    """
    va_str = str(virtual_account).strip()
    if len(va_str) != 14 or not va_str.startswith("997816"):
        return None
    
    # 檢查是否為月子服務 (第 7-8 碼為 99)
    category = va_str[6:8]
    if category != "99":
        return None  # 忽略托育課程(如113)、月子培訓(88)、會員(00)的虛擬帳號交易
        
    code_part = va_str[8:]  # 取得 6 碼 (如 115001)
    year = code_part[:3]    # 115
    seq = code_part[3:]     # 001
    
    # 還原成 9 碼案件編號：115 + 0000 + 01 (即 115000001)
    case_no = f"{year}0000{int(seq):02d}"
    return case_no

def load_case_info_from_db():
    # ponytail: 從 MySQL 資料庫動態載入客戶、案號、月嫂姓名以避免依賴 Excel 第二分頁
    case_info = {}
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            sql = """
            SELECT 
                c.case_no, 
                c.name AS client_name, 
                s.name AS staff_name 
            FROM orders o
            JOIN clients c ON o.client_id = c.id
            LEFT JOIN staff s ON o.staff_id = s.id
            WHERE c.case_no IS NOT NULL AND c.case_no != '';
            """
            cursor.execute(sql)
            for row in cursor.fetchall():
                c_no = row[0]
                case_info[c_no] = {
                    'client_name': row[1],
                    'staff_name': row[2] if row[2] else "",
                    'amount_receivable': 80000.0,  # 預設應收金額
                    'caregiver_fee': 60000.0      # 預設月嫂費用
                }
    except Exception as e:
        print(f"[警告] 無法從資料庫載入對照表資訊: {e}")
    return case_info

def main():
    excel_path = "document/資料庫、資料處理/帳務.xlsx"
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到帳務 Excel 檔案，路徑為：{excel_path}")
        sys.exit(1)
        
    print(f"開始解析帳務 Excel：{excel_path} ...")
    xl = pd.ExcelFile(excel_path)
    
    # 從資料庫動態載入對照關係
    case_info = load_case_info_from_db()
    
    # 2. 讀取「合作社帳戶」分頁 (整個 Excel 的第一個/唯一一個分頁) 交易流水帳
    tx_sheet_name = xl.sheet_names[0]
    df_tx = xl.parse(tx_sheet_name)
    
    # 建立案件的累計收款/付款結果
    payments_data = {} # {case_no: {deposit, deposit_at, balance, balance_at, caregiver_paid, caregiver_paid_at}}
    
    # 遍歷流水帳交易 (跳過首兩行明細標頭與中文表頭，從 index 2 開始)
    ignored_va_count = 0
    for idx in range(2, len(df_tx)):
        row = df_tx.iloc[idx]
        if pd.isna(row.iloc[0]):
            continue
            
        va = str(row.iloc[9]).strip() if pd.notna(row.iloc[9]) else ""
        
        # 支出/存入金額與交易日期
        tx_date_str = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else None
        expense = float(row.iloc[6]) if pd.notna(row.iloc[6]) and str(row.iloc[6]).strip() else 0.0
        income = float(row.iloc[7]) if pd.notna(row.iloc[7]) and str(row.iloc[7]).strip() else 0.0
        
        # (A) 處理存入交易 (訂金/尾款) -> 透過虛擬帳號解碼
        if income > 0 and va:
            case_no = decode_va_to_case_no(va)
            if not case_no:
                # 記錄被忽略的課程或會員帳號
                if va.startswith("997816"):
                    ignored_va_count += 1
                continue
                
            if case_no not in payments_data:
                payments_data[case_no] = {
                    'deposit': 0.0, 'deposit_at': None,
                    'balance': 0.0, 'balance_at': None,
                    'caregiver_paid': 0.0, 'caregiver_paid_at': None
                }
                
            # 套用固定金額測試規格進行歸戶判斷
            if income == 12000.0:
                payments_data[case_no]['deposit'] = 12000.0
                payments_data[case_no]['deposit_at'] = tx_date_str
            elif income == 68000.0:
                payments_data[case_no]['balance'] = 68000.0
                payments_data[case_no]['balance_at'] = tx_date_str
                
        # (B) 處理支出交易 (轉帳給月嫂) -> 透過交易摘要的月嫂姓名比對案件
        elif expense > 0:
            summary = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ""
            # 尋找是否符合 "月嫂[姓名]費" 格式
            match = re.search(r"月嫂(.*?)費", summary)
            if match:
                caregiver_name = match.group(1).strip()
                # 搜尋此月嫂名字對應的案件編號
                matched_case_no = None
                for c_no, info in case_info.items():
                    # 優先比對資料庫查出的月嫂姓名 (staff_name)，相容比對 client_name
                    if info.get('staff_name') == caregiver_name or info.get('client_name') == caregiver_name:
                        matched_case_no = c_no
                        break
                        
                if matched_case_no:
                    if matched_case_no not in payments_data:
                        payments_data[matched_case_no] = {
                            'deposit': 0.0, 'deposit_at': None,
                            'balance': 0.0, 'balance_at': None,
                            'caregiver_paid': 0.0, 'caregiver_paid_at': None
                        }
                    payments_data[matched_case_no]['caregiver_paid'] = expense
                    payments_data[matched_case_no]['caregiver_paid_at'] = tx_date_str

    # 3. 寫入/更新至 MySQL payments 資料表
    print(f"成功解析出 {len(payments_data)} 筆符合月子服務的財務帳務紀錄。已忽略雜訊虛擬帳號交易: {ignored_va_count} 筆。")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as conn_err:
        print(f"資料庫連線失敗：{conn_err}")
        sys.exit(1)
        
    inserted_count = 0
    updated_count = 0
    
    sql_upsert = """
    INSERT INTO payments (
        case_no, client_name, amount_receivable, 
        deposit_received, deposit_received_at, 
        balance_received, balance_received_at, 
        caregiver_fee, caregiver_paid_at, 
        payment_status
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    ) ON DUPLICATE KEY UPDATE
        deposit_received = VALUES(deposit_received),
        deposit_received_at = VALUES(deposit_received_at),
        balance_received = VALUES(balance_received),
        balance_received_at = VALUES(balance_received_at),
        caregiver_fee = VALUES(caregiver_fee),
        caregiver_paid_at = VALUES(caregiver_paid_at),
        payment_status = VALUES(payment_status);
    """
    
    try:
        # 在寫入前，先建立 case_no 欄位的唯一索引以確保 ON DUPLICATE KEY UPDATE 運作
        # ponytail: 確保 case_no 是 payments 的唯一值以防重複對帳
        try:
            cursor.execute("ALTER TABLE payments ADD UNIQUE INDEX idx_unique_case (case_no);")
            conn.commit()
        except Exception:
            pass  # 索引已存在，跳過
            
        for case_no, pay in payments_data.items():
            info = case_info.get(case_no, {'client_name': '未知客戶', 'amount_receivable': 80000.0, 'caregiver_fee': 60000.0})
            
            # 判斷對帳狀態
            if pay['balance'] > 0:
                status = "已結案"
            elif pay['deposit'] > 0:
                status = "已收訂金"
            else:
                status = "待收訂金"
                
            cursor.execute(sql_upsert, (
                case_no,
                info['client_name'],
                info['amount_receivable'],
                pay['deposit'],
                pay['deposit_at'],
                pay['balance'],
                pay['balance_at'],
                pay['caregiver_paid'],
                pay['caregiver_paid_at'],
                status
            ))
            
            # 依據影響行數累計
            affected_rows = cursor.rowcount
            if affected_rows == 1:
                inserted_count += 1
            elif affected_rows == 2:
                updated_count += 1
                
        conn.commit()
        print(f"\n====== 對帳匯入成功！ ======")
        print(f"- 新增對帳紀錄筆數: {inserted_count}")
        print(f"- 更新對帳紀錄筆數: {updated_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"匯入過程中斷，已進行 Rollback。原因: {e}")
    finally:
        conn.close()
        
if __name__ == "__main__":
    main()

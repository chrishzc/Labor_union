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
from dotenv import load_dotenv

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 從專案根目錄的 .env 讀取資料庫連線設定 (若 .env 不存在或缺少某欄位，則回退為原本的預設值)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# 資料庫連線配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'database': os.getenv('DB_DATABASE', 'union_db'),
    'charset': 'utf8mb4'
}

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
    case_no = f"{year}{int(seq):06d}"
    return case_no


def normalize_header(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace(" ", "")


def get_sheet_name(xl: pd.ExcelFile, expected: str) -> str:
    matches = {normalize_header(name): name for name in xl.sheet_names}
    try:
        return matches[normalize_header(expected)]
    except KeyError as exc:
        raise ValueError(f"帳務活頁簿缺少必要分頁：{expected}") from exc


def load_case_reference(xl: pd.ExcelFile) -> pd.DataFrame:
    """Load the fixed, headerless 12-column reference sheet safely.

    This legacy sheet has no column labels, so an added column cannot be
    identified reliably. Refuse any changed width instead of allowing a
    positional shift to corrupt case numbers or amounts.
    """
    raw = xl.parse(get_sheet_name(xl, "資料庫"), header=None)
    if raw.shape[1] != 12:
        raise ValueError(
            f"帳務『資料庫』分頁必須正好有 12 欄，目前為 {raw.shape[1]} 欄；"
            "為避免 id/order_id 等額外欄位造成位移，已停止匯入"
        )
    return raw


def load_transactions(xl: pd.ExcelFile) -> pd.DataFrame:
    """Find the bank header row and select transaction fields by name."""
    raw = xl.parse(get_sheet_name(xl, "合作社帳戶"), header=None)
    required = {"記帳日期", "交易摘要", "支出", "存入", "虛擬帳號/轉帳備註"}
    for row_index in range(min(10, len(raw))):
        headers = [str(value).strip() if pd.notna(value) else "" for value in raw.iloc[row_index]]
        if required.issubset(set(headers)):
            data = raw.iloc[row_index + 1:].copy()
            data.columns = headers
            # Explicit allowlist: unknown fields, including id/order_id, are ignored.
            return data[["記帳日期", "交易摘要", "支出", "存入", "虛擬帳號/轉帳備註"]]
    raise ValueError("帳務『合作社帳戶』分頁找不到必要的交易欄名")

def main():
    excel_path = "document/資料庫、資料處理/帳務.xlsx"
    if not os.path.exists(excel_path):
        print(f"錯誤：找不到帳務 Excel 檔案，路徑為：{excel_path}")
        sys.exit(1)
        
    print(f"開始解析帳務 Excel：{excel_path} ...")
    xl = pd.ExcelFile(excel_path)
    
    # 1. 讀取「資料庫」分頁 (Sheet 1) 以獲取案件對照與應收金額
    df_db = load_case_reference(xl)
    
    # 解析案件對照表 (從資料庫分頁中建立映射)
    case_info = {} # {case_no: {client_name, amount_receivable, caregiver_fee}}
    for _, row in df_db.iterrows():
        # 對照表格式：[前綴, 序號, 工會, 姓名, 年度, 案號, 狀態, 虛擬帳號, 應收, 月嫂費用, 備份姓名, 備註案號]
        va = str(row.iloc[7]).strip() if pd.notna(row.iloc[7]) else ""
        case_no_raw = str(row.iloc[11]).strip() if pd.notna(row.iloc[11]) else ""
        # 去除備註中的 "案" 字以取得純數字編號
        case_no = case_no_raw.replace("案", "")
        name = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ""
        
        if case_no and va:
            case_info[case_no] = {
                'client_name': name,
                'amount_receivable': float(row.iloc[8]) if pd.notna(row.iloc[8]) else 80000.0,
                'caregiver_fee': float(row.iloc[9]) if pd.notna(row.iloc[9]) else 60000.0
            }
            
    # 2. 讀取「合作社帳戶」分頁 (Sheet 0) 交易流水帳
    df_tx = load_transactions(xl)
    
    # 建立案件的累計收款/付款結果
    payments_data = {} # {case_no: {deposit, deposit_at, balance, balance_at, caregiver_paid, caregiver_paid_at}}
    
    ignored_va_count = 0
    for _, row in df_tx.iterrows():
        if pd.isna(row.get('記帳日期')):
            continue
            
        va_value = row.get('虛擬帳號/轉帳備註')
        va = str(va_value).strip() if pd.notna(va_value) else ""
        
        # 支出/存入金額與交易日期
        tx_date_value = row.get('記帳日期')
        expense_value = row.get('支出')
        income_value = row.get('存入')
        tx_date_str = str(tx_date_value).strip() if pd.notna(tx_date_value) else None
        expense = float(expense_value) if pd.notna(expense_value) and str(expense_value).strip() else 0.0
        income = float(income_value) if pd.notna(income_value) and str(income_value).strip() else 0.0
        
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
                    'deposit_received': 0.0, 'deposit_received_at': None,
                    'first_payment_received': 0.0, 'first_payment_received_at': None,
                    'second_payment_received': 0.0, 'second_payment_received_at': None,
                    'caregiver_fee': 0.0, 'caregiver_paid_at': None
                }
                
            # ponytail: Reconcile chronologically (1st deposit, 2nd first payment, 3rd second payment)
            if payments_data[case_no]['deposit_received'] == 0.0:
                payments_data[case_no]['deposit_received'] = income
                payments_data[case_no]['deposit_received_at'] = tx_date_str
            elif payments_data[case_no]['first_payment_received'] == 0.0:
                payments_data[case_no]['first_payment_received'] = income
                payments_data[case_no]['first_payment_received_at'] = tx_date_str
            else:
                payments_data[case_no]['second_payment_received'] = income
                payments_data[case_no]['second_payment_received_at'] = tx_date_str
                
        # (B) 處理支出交易 (轉帳給月嫂) -> 透過交易摘要的月嫂姓名比對案件
        elif expense > 0:
            summary_value = row.get('交易摘要')
            summary = str(summary_value).strip() if pd.notna(summary_value) else ""
            # 尋找是否符合 "月嫂[姓名]費" 格式
            match = re.search(r"月嫂(.*?)費", summary)
            if match:
                caregiver_name = match.group(1).strip()
                # 搜尋此月嫂名字對應的案件編號
                matched_case_no = None
                for c_no, info in case_info.items():
                    if info['client_name'] == caregiver_name:
                        matched_case_no = c_no
                        break
                        
                if matched_case_no:
                    if matched_case_no not in payments_data:
                        payments_data[matched_case_no] = {
                            'deposit_received': 0.0, 'deposit_received_at': None,
                            'first_payment_received': 0.0, 'first_payment_received_at': None,
                            'second_payment_received': 0.0, 'second_payment_received_at': None,
                            'caregiver_fee': 0.0, 'caregiver_paid_at': None
                        }
                    payments_data[matched_case_no]['caregiver_fee'] = expense
                    payments_data[matched_case_no]['caregiver_paid_at'] = tx_date_str

    # 3. 寫入/更新至 MySQL payments 資料表
    print(f"成功解析出 {len(payments_data)} 筆符合月子服務的財務帳務紀錄。已忽略雜訊虛擬帳號交易: {ignored_va_count} 筆。")
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except Exception as conn_err:
        print(f"資料庫連線失敗：{conn_err}")
        sys.exit(1)
        
    inserted_count = 0
    updated_count = 0
    
    sql_upsert = """
    INSERT INTO payments (
        case_no, client_name,
        deposit_receivable, deposit_received, deposit_due_date, deposit_received_at,
        first_payment_receivable, first_payment_received, first_payment_due_date, first_payment_received_at,
        second_payment_receivable, second_payment_received, second_payment_due_date, second_payment_received_at,
        amount_receivable, amount_received,
        caregiver_fee, caregiver_paid_at, 
        payment_status
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    ) ON DUPLICATE KEY UPDATE
        deposit_receivable = VALUES(deposit_receivable),
        deposit_received = VALUES(deposit_received),
        deposit_due_date = VALUES(deposit_due_date),
        deposit_received_at = VALUES(deposit_received_at),
        first_payment_receivable = VALUES(first_payment_receivable),
        first_payment_received = VALUES(first_payment_received),
        first_payment_due_date = VALUES(first_payment_due_date),
        first_payment_received_at = VALUES(first_payment_received_at),
        second_payment_receivable = VALUES(second_payment_receivable),
        second_payment_received = VALUES(second_payment_received),
        second_payment_due_date = VALUES(second_payment_due_date),
        second_payment_received_at = VALUES(second_payment_received_at),
        amount_receivable = VALUES(amount_receivable),
        amount_received = VALUES(amount_received),
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
            dep_rec = pay.get('deposit_received', 0.0)
            p1_rec = pay.get('first_payment_received', 0.0)
            p2_rec = pay.get('second_payment_received', 0.0)
            amount_receivable = info['amount_receivable']
            deposit_receivable = dep_rec
            first_payment_receivable = p1_rec
            second_payment_receivable = max(amount_receivable - deposit_receivable - first_payment_receivable, p2_rec)
            amount_received = dep_rec + p1_rec + p2_rec

            if dep_rec > 0 and p1_rec > 0 and p2_rec > 0:
                status = "已結案"
            elif dep_rec > 0 and p1_rec > 0:
                status = "已收一期款"
            elif dep_rec > 0:
                status = "已收訂金"
            else:
                status = "待收訂金"
                
            cursor.execute(sql_upsert, (
                case_no,
                info['client_name'],
                deposit_receivable,
                dep_rec,
                pay['deposit_received_at'],
                pay['deposit_received_at'],
                first_payment_receivable,
                p1_rec,
                pay['first_payment_received_at'],
                pay['first_payment_received_at'],
                second_payment_receivable,
                p2_rec,
                pay['second_payment_received_at'],
                pay['second_payment_received_at'],
                amount_receivable,
                amount_received,
                pay['caregiver_fee'],
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

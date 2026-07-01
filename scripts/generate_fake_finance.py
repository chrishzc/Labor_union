# -*- coding: utf-8 -*-
"""
File: scripts/generate_fake_finance.py
Description: 模擬生成帳務.xlsx 的測試假資料，包含「合作社帳戶」(流水帳) 與「資料庫」(案件財務對照表)。
ponytail: 帳務公式未建，目前金額與尾款全數採用固定數值進行 Pipe 測試。
"""
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def main():
    print("正在準備生成假帳務資料...")
    
    # 產生的資料夾路徑
    output_dir = "document/資料庫、資料處理"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "帳務.xlsx")
    
    # 1. 定義 10 筆測試用的案件編號
    # 案件編號 (查詢序號)：年度 (3碼) + 6碼流水號
    base_cases = [f"1150000{i:02d}" for i in range(1, 11)]
    client_names = ["林沛晴", "陳美婷", "張雅涵", "吳欣宜", "黃茹宣", "蔡欣怡", "楊宇廷", "許冠宇", "林明憲", "賴廷豪"]
    
    # 2. 生成「資料庫」分頁 (案件對照表)
    # 欄位順序對照：
    # HC, 序號, 工會名稱, 客戶姓名, 年度, 案號後三碼, 狀態, 虛擬帳號, 應收總額, 月嫂費用, 備註
    db_rows = []
    for idx, case_no in enumerate(base_cases):
        seq = idx + 1
        name = client_names[idx]
        
        # 虛擬帳號後 6 碼為：年度 (115) + 流水號後三碼 (001-010)
        va_suffix = f"115{seq:03d}"
        virtual_account = f"99781699{va_suffix}"
        
        # ponytail: 金額依規則全部固定數值
        amount_receivable = 80000
        caregiver_fee = 60000
        
        db_rows.append([
            "HC",             # 案件前綴
            seq,              # 序號
            "新竹市月子服務工會",# 工會名
            name,             # 客戶姓名
            115.0,            # 年度
            seq,              # 案號
            1.0,              # 狀態
            virtual_account,  # 虛擬帳號 (14碼)
            amount_receivable,# 應收總額 (固定 80,000)
            caregiver_fee,    # 月嫂服務費 (固定 60,000)
            name,             # 客戶姓名備份
            f"{case_no}案"     # 備註
        ])
        
    df_db = pd.DataFrame(db_rows)
    # 本地 Excel 來源沒有表頭，為 DataFrame 提供預設的 Unnamed 欄位名稱以符合解析習慣
    df_db.columns = [f"Unnamed: {i}" for i in range(df_db.shape[1])]
    
    # 3. 生成「合作社帳戶」分頁 (銀行流水帳明細)
    # 欄位：帳號, 交易時間, 記帳日期, 入帳日期, 交易摘要, 幣別, 支出, 存入, 餘額, 虛擬帳號/轉帳備註, 備用欄位
    tx_rows = []
    base_account = "03201800231313"
    current_balance = 500000.0
    
    # 第一行放標頭資訊，模擬銀行匯出檔首行
    tx_rows.append([
        "帳號/姓名:03201800231313 新竹市月子照顧服務人員職業工會\n帳戶:03201800231313 TWD\n區間:2026/07/01 00:00~2026/07/31 23:59",
        None, None, None, None, None, None, None, "列印時間:2026/08/01 10:00:00", None, None
    ])
    
    # 第二行放中文表頭
    tx_rows.append([
        "帳號", "交易時間", "記帳日期", "入帳日期", "交易摘要", "幣別", "支出", "存入", "餘額", "虛擬帳號/轉帳備註", "備用"
    ])
    
    # 依序為 10 筆案件生成：
    # 1. 存入訂金 12,000
    # 2. 存入尾款 68,000 (部分案件)
    # 3. 支出月嫂費用 60,000 (部分案件)
    for idx, case_no in enumerate(base_cases):
        seq = idx + 1
        va_suffix = f"115{seq:03d}"
        va = f"99781699{va_suffix}"
        
        # 訂金交易時間
        tx_time_dep = f"2026/07/{seq:02d} 10:00:00"
        tx_date_dep = f"2026/07/{seq:02d}"
        
        # 1. 存入訂金 (固定 12,000)
        current_balance += 12000
        tx_rows.append([
            base_account, tx_time_dep, tx_date_dep, tx_date_dep, "虛擬帳入", "TWD", None, 12000, current_balance, va, None
        ])
        
        # 只有前 5 筆案件模擬已收尾款與撥款給月嫂
        if seq <= 5:
            # 尾款交易時間
            tx_time_bal = f"2026/07/{seq+10:02d} 14:00:00"
            tx_date_bal = f"2026/07/{seq+10:02d}"
            
            # 2. 存入尾款 (固定 68,000)
            current_balance += 68000
            tx_rows.append([
                base_account, tx_time_bal, tx_date_bal, tx_date_bal, "虛擬帳入", "TWD", None, 68000, current_balance, va, None
            ])
            
            # 撥款月嫂時間
            tx_time_pay = f"2026/07/{seq+15:02d} 16:00:00"
            tx_date_pay = f"2026/07/{seq+15:02d}"
            
            # 3. 支出月嫂費用 (固定 60,000)
            current_balance -= 60000
            tx_rows.append([
                base_account, tx_time_pay, tx_date_pay, tx_date_pay, "合作社支", "TWD", 60000, None, current_balance, f"月嫂{client_names[idx]}費", None
            ])
            
    # 4. 混雜非月子服務的虛擬帳號交易 (課程/會員費雜訊，用以驗證過濾邏輯)
    # 托育課程
    current_balance += 5000
    tx_rows.append([
        base_account, "2026/07/28 11:00:00", "2026/07/28", "2026/07/28", "虛擬帳入", "TWD", None, 5000, current_balance, "99781611302045", None
    ])
    # 會員常年會費
    current_balance += 2000
    tx_rows.append([
        base_account, "2026/07/29 15:30:00", "2026/07/29", "2026/07/29", "虛擬帳入", "TWD", None, 2000, current_balance, "99781600004567", None
    ])
    
    df_tx = pd.DataFrame(tx_rows)
    # 為 Sheet 0 提供預設的 Unnamed 欄位名稱
    df_tx.columns = [f"Unnamed: {i}" for i in range(df_tx.shape[1])]
    
    # 4. 寫入多分頁 Excel 檔案
    # 使用 openpyxl 引擎寫入，工作表名稱必須與本地一致
    # 第一張工作表: 合作社帳戶 (Sheet 0)，第二張工作表: 資料庫 (Sheet 1)
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_tx.to_excel(writer, sheet_name="合作社帳戶", index=False)
        df_db.to_excel(writer, sheet_name="資料庫", index=False)
        
    print(f"成功生成測試用假帳務 Excel！已寫入至: {output_file}")
    print("本假資料包含 10 個案件之訂金明細，其中 5 個案件包含尾款與撥款，並混入課程/會員費虛擬帳號以驗證對帳過濾邏輯。")

if __name__ == "__main__":
    main()

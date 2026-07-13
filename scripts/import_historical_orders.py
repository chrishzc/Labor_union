# -*- coding: utf-8 -*-
import os
import sys
import pandas as pd
import pymysql
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# 讀取環境變數
load_dotenv()

# 取得資料庫配置
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_DATABASE = os.getenv("DB_DATABASE", "union_db")

def parse_excel_date(val):
    if pd.isna(val) or val == "" or str(val).strip() == "":
        return None
    try:
        # 若為 Excel 數值型態日期 (以 1899-12-30 為基準)
        num_val = float(val)
        return (datetime(1899, 12, 30) + timedelta(days=int(num_val))).date()
    except (ValueError, TypeError):
        # 若為一般日期字串 (如 2025/6/4)
        try:
            return pd.to_datetime(val).date()
        except:
            return None

def map_status(val):
    if pd.isna(val) or val == "" or str(val).strip() == "":
        return "訂單取消"
    try:
        status_num = int(float(val))
        if status_num == 0:
            return "訂單取消"
        elif status_num == 1:
            return "訂單完成"
        elif status_num == 2:
            return "洽談中"
    except (ValueError, TypeError):
        pass
    return "洽談中"

def main():
    if len(sys.argv) < 2:
        print("使用方式: python scripts/import_historical_orders.py <excel_file_path>")
        sys.exit(1)
        
    excel_path = sys.argv[1]
    if not os.path.exists(excel_path):
        print(f"錯誤: 找不到 Excel 檔案 {excel_path}")
        sys.exit(1)
        
    try:
        # header=None 表示第一行就是資料
        df = pd.read_excel(excel_path, header=None)
    except Exception as e:
        print(f"錯誤: 無法讀取 Excel 檔案 - {str(e)}")
        sys.exit(1)
        
    print(f"成功讀取 Excel 檔案，共 {len(df)} 筆資料。開始進行資料更新...")
    
    conn = None
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"錯誤: 無法連線至資料庫 - {str(e)}")
        sys.exit(1)
        
    warnings = []
    success_count = 0
    
    with conn.cursor() as cursor:
        for idx, row in df.iterrows():
            line_num = idx + 1
            # 欄位解析，防範欄位不足或 NaN
            client_name = str(row[0]).strip() if len(row) > 0 and not pd.isna(row[0]) else None
            case_no = str(row[1]).strip() if len(row) > 1 and not pd.isna(row[1]) else None
            start_date_raw = row[2] if len(row) > 2 else None
            # 欄位 4 (行[3]): 服務結束時間，因只更新這三個指定欄位，此欄位暫不寫入資料庫
            # 欄位 5 (行[4]): status
            status_raw = row[4] if len(row) > 4 else None
            # 欄位 6 (行[5]): staff_name
            staff_name = str(row[5]).strip() if len(row) > 5 and not pd.isna(row[5]) else None
            
            if not client_name:
                warnings.append(f"第 {line_num} 行：缺少客戶姓名，已跳過該行。")
                continue
                
            # 判斷是否有案件編號
            if not case_no:
                # 案件編號為空，但有姓名：僅將該姓名對應的訂單狀態改為 "訂單取消"
                cursor.execute("SELECT id FROM clients WHERE name = %s", (client_name,))
                client_res = cursor.fetchall()
                
                if not client_res:
                    warnings.append(f"第 {line_num} 行：無案件編號，且在資料庫中找不到客戶「{client_name}」，已跳過。")
                    continue
                    
                updated_any = False
                for c_row in client_res:
                    c_id = c_row['id']
                    cursor.execute("SELECT id FROM orders WHERE client_id = %s", (c_id,))
                    order_res_list = cursor.fetchall()
                    
                    for o_row in order_res_list:
                        o_id = o_row['id']
                        try:
                            cursor.execute("UPDATE orders SET status = '訂單取消' WHERE id = %s", (o_id,))
                            success_count += 1
                            updated_any = True
                        except Exception as e:
                            warnings.append(f"第 {line_num} 行：更新客戶「{client_name}」訂單狀態為取消時出錯 - {str(e)}")
                            
                if not updated_any:
                    warnings.append(f"第 {line_num} 行：無案件編號，雖然找到客戶「{client_name}」，但該客戶在資料庫中無任何訂單紀錄，已跳過。")
                continue
                
            # 1. 查詢 client 與 order
            cursor.execute("""
                SELECT o.id AS order_id FROM orders o
                JOIN clients c ON o.client_id = c.id
                WHERE c.name = %s AND c.case_no = %s
            """, (client_name, case_no))
            order_res = cursor.fetchone()
            
            if not order_res:
                warnings.append(f"第 {line_num} 行：客戶「{client_name}」(案號 {case_no}) 在資料庫中找不到對應的訂單，已跳過更新。")
                continue
                
            order_id = order_res['order_id']
            
            # 2. 查詢 staff_id
            staff_id = None
            if staff_name:
                cursor.execute("SELECT id FROM staff WHERE name = %s", (staff_name,))
                staff_res = cursor.fetchone()
                if staff_res:
                    staff_id = staff_res['id']
                else:
                    warnings.append(f"第 {line_num} 行：找不到服務人員「{staff_name}」，對應之 staff_id 將設為 NULL。")
            
            # 3. 轉換開始時間
            actual_start_date = parse_excel_date(start_date_raw)
            if start_date_raw and not actual_start_date:
                warnings.append(f"第 {line_num} 行：開始日期格式無法解析 (原始值: {start_date_raw})，將設為 NULL。")
            
            # 4. 轉換狀態碼
            status = map_status(status_raw)
            
            # 5. 更新訂單
            try:
                cursor.execute("""
                    UPDATE orders
                    SET actual_start_date = %s, status = %s, staff_id = %s
                    WHERE id = %s
                """, (actual_start_date, status, staff_id, order_id))
                success_count += 1
            except Exception as e:
                warnings.append(f"第 {line_num} 行：寫入資料庫時出錯 - {str(e)}")
                
        conn.commit()
        
    conn.close()
    
    print("-" * 60)
    print(f"更新完成！成功更新 {success_count} 筆訂單。")
    if warnings:
        print(f"共有 {len(warnings)} 筆警告與錯誤資訊：")
        for w in warnings:
            print(f"⚠️ {w}")
    else:
        print("無任何警告與錯誤。")
    print("-" * 60)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import pandas as pd

def inspect_csv(path, output_file):
    output_file.write(f"\n==================== CSV 檔案: {path} ====================\n")
    try:
        # 使用 utf-8 或是 cp950 (Big5) 讀取 CSV
        try:
            df = pd.read_csv(path, encoding='utf-8')
        except Exception:
            df = pd.read_csv(path, encoding='cp950')
        output_file.write(f"欄位數量: {len(df.columns)}\n")
        output_file.write(f"資料筆數: {len(df)}\n")
        output_file.write(f"欄位列表: {list(df.columns)}\n")
        output_file.write("範例資料 (前 5 行):\n")
        output_file.write(df.head(5).to_string() + "\n")
    except Exception as e:
        output_file.write(f"CSV 讀取失敗: {e}\n")

def inspect_excel(path, output_file):
    output_file.write(f"\n==================== EXCEL 檔案: {path} ====================\n")
    try:
        xl = pd.ExcelFile(path)
        output_file.write(f"工作表名稱 (Sheets): {xl.sheet_names}\n")
        for sheet in xl.sheet_names:
            output_file.write(f"\n--- 工作表: {sheet} ---\n")
            df = xl.parse(sheet)
            output_file.write(f"欄位數量: {len(df.columns)}\n")
            output_file.write(f"資料筆數: {len(df)}\n")
            cols = [str(c) for c in df.columns]
            output_file.write(f"欄位列表: {cols[:20]} ... (共 {len(df.columns)} 個)\n" if len(df.columns) > 20 else f"欄位列表: {cols}\n")
            output_file.write("範例資料 (前 3 行):\n")
            output_file.write(df.head(3).to_string() + "\n")
    except Exception as e:
        output_file.write(f"EXCEL 讀取失敗: {e}\n")

with open("scratch/excel_report.txt", "w", encoding="utf-8") as f:
    inspect_csv("document/資料庫、資料處理/訂單系統.csv", f)
    inspect_excel("document/管理端UI/表格需求模板/所需表格.xlsx", f)

print("重新檢查分析完成，已寫入至 scratch/excel_report.txt")

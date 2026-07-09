"""
================================================================================
檢查 SQL 資料庫中 JSON / notes 實體欄位內容與鍵值對齊腳本
================================================================================
"""
import sqlite3
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(project_root, "db", "lobar_union.db")

def inspect_db():
    sys.stdout.reconfigure(encoding='utf-8')
    print("==========================================================")
    print("🔍 檢查 SQL 資料庫 (lobar_union.db) 實體 JSON/notes 內容")
    print("==========================================================")
    
    if not os.path.exists(db_path):
        print(f"❌ 找不到資料庫檔案: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. 檢查有哪些表格
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"📁 發現表格: {tables}")

    # 2. 探查 beclass_records, orders, clients 等表格中的 notes 或 raw 欄位
    for t in ['beclass_records', 'orders', 'clients', 'matching_records']:
        if t in tables:
            print(f"\n----------------------------------------------------------")
            print(f"📊 表格【{t}】結構與內容抽樣：")
            cursor.execute(f"PRAGMA table_info({t});")
            cols = [c[1] for c in cursor.fetchall()]
            print(f"  欄位清單: {cols}")
            
            cursor.execute(f"SELECT * FROM {t} LIMIT 3;")
            rows = cursor.fetchall()
            for r_idx, r in enumerate(rows):
                row_dict = dict(zip(cols, r))
                print(f"\n  [Sample {r_idx+1}]:")
                for k, v in row_dict.items():
                    if v and ('json' in k.lower() or 'note' in k.lower() or 'detail' in k.lower() or 'raw' in k.lower() or str(v).startswith('{')):
                        print(f"    👉 {k}: {v}")

    conn.close()

if __name__ == "__main__":
    inspect_db()

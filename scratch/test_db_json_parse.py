"""
================================================================================
MySQL 實體資料庫 JSON / notes 探查腳本
================================================================================
"""
import sys
import os
import json
import pymysql

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services import db_service

def test_parse():
    sys.stdout.reconfigure(encoding='utf-8')
    print("==========================================================")
    print("🔍 嘗試連線 MySQL 探查 v_order_details / beclass_records JSON 內容")
    print("==========================================================")
    
    try:
        conn = db_service.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            tables = [list(r.values())[0] for r in cursor.fetchall()]
            print(f"📁 MySQL 發現表格: {tables}")
            
            # 檢視 satisfy beclass_records 或 orders 的 raw json
            for t in ['orders', 'beclass_records', 'v_order_details']:
                if t in tables:
                    print(f"\n----------------------------------------------------------")
                    print(f"📊 檢查表格/視圖【{t}】：")
                    cursor.execute(f"SELECT * FROM `{t}` LIMIT 3;")
                    rows = cursor.fetchall()
                    for idx, r in enumerate(rows):
                        print(f"\n  [Record #{idx+1}]:")
                        for k, v in r.items():
                            if v and ('note' in k.lower() or 'detail' in k.lower() or 'json' in k.lower() or str(v).startswith('{')):
                                print(f"    👉 {k}: {v}")
        conn.close()
    except Exception as e:
        print(f"⚠️ 連線 MySQL 失敗（可能 MySQL 伺服器未啟動或環境為沙盒）: {e}")
        print("💡 將自動轉向備用解析測試！")

if __name__ == "__main__":
    test_parse()

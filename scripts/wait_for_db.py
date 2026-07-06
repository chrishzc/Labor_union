# -*- coding: utf-8 -*-
"""
專案名稱: Lobar_union
檔案名稱: scripts/wait_for_db.py
描述: 輪詢探測 MySQL 3306 埠，確認資料庫已初始化並可接受連線，防範後續腳本連線逾時。
"""
import time
import sys
import pymysql

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def main():
    print("⏳ 正在等待 MySQL 資料庫啟動完成 (最長等待 30 秒)...")
    t = 0
    while t < 30:
        try:
            conn = pymysql.connect(
                host='127.0.0.1',
                port=3306,
                user='root',
                password='1234',
                charset='utf8mb4'
            )
            conn.close()
            print("🟢 MySQL 資料庫已就緒，可以開始執行初始化與匯入！")
            sys.exit(0)
        except Exception:
            time.sleep(1)
            t += 1
    print("❌ 錯誤：無法連線至 MySQL，請確認 MySQL 容器是否正常運作！")
    sys.exit(1)

if __name__ == '__main__':
    main()

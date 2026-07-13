# -*- coding: utf-8 -*-
"""
專案名稱: Lobar_union
檔案名稱: scripts/wait_for_db.py
描述: 輪詢探測 MySQL 3306 埠，確認資料庫已初始化並可接受連線，防範後續腳本連線逾時。
"""
import os
import time
import sys
import pymysql
from dotenv import load_dotenv

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 從專案根目錄的 .env 讀取資料庫連線設定 (若 .env 不存在或缺少某欄位，則回退為原本的預設值)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

def main():
    print("⏳ 正在等待 MySQL 資料庫啟動完成 (最長等待 30 秒)...")
    t = 0
    while t < 30:
        try:
            conn = pymysql.connect(
                host=os.getenv('DB_HOST', '127.0.0.1'),
                port=int(os.getenv('DB_PORT', 3306)),
                user=os.getenv('DB_USER', 'root'),
                password=os.getenv('DB_PASSWORD', '1234'),
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

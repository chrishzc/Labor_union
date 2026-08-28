# -*- coding: utf-8 -*-
"""
專案名稱: Lobar_union
檔案名稱: scripts/wait_for_db.py
描述: 依專案 .env 輪詢指定 MySQL database，確認 current gate 使用的同一目標可接受連線。
"""
import os
import sys
import time
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_preserved_database_additive_schema import (
    DatabaseConfig,
    config_from_env,
)

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

ENVIRONMENT_FILE = PROJECT_ROOT / ".env"


def configured_target(
    environment_file: Path = ENVIRONMENT_FILE,
) -> tuple[DatabaseConfig, str]:
    """Read the same strict .env target as the local database updater."""
    if environment_file.is_file():
        config, database = config_from_env(environment_file)
    else:
        config = DatabaseConfig(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
        )
        database = os.getenv("DB_DATABASE", "").strip()
    if not database:
        raise ValueError("DB_DATABASE is required for local database readiness")
    return config, database

def main():
    try:
        config, database = configured_target()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"❌ 錯誤：無法讀取本機資料庫目標：{exc}")
        sys.exit(1)
    print(f"⏳ 正在等待 MySQL 資料庫 {database} 啟動完成 (最長等待 30 秒)...")
    t = 0
    while t < 30:
        try:
            conn = pymysql.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                database=database,
                charset='utf8mb4',
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

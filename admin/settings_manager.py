# -*- coding: utf-8 -*-
"""
File: admin/settings_manager.py
Description: 系統全域動態設定管理器，負責從資料庫存取設定與動態安裝依賴套件。
"""
import sys
import os
import subprocess
import pymysql

# 確保可以匯入 admin.utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from admin.utils import get_db_connection

def get_setting(key: str, default_value: str = None) -> str:
    """從資料庫獲取設定值，若不存在則回傳預設值"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 確認表是否存在
            try:
                cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = %s", (key,))
                result = cursor.fetchone()
                if result:
                    return result[0]
            except pymysql.err.ProgrammingError:
                pass # 表可能還沒建立
            return default_value
    finally:
        conn.close()

def set_setting(key: str, value: str, description: str = ""):
    """寫入或更新設定值至資料庫"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO system_settings (setting_key, setting_value, description)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    setting_value = VALUES(setting_value),
                    description = IF(VALUES(description) != '', VALUES(description), description)
            """, (key, str(value), description))
            conn.commit()
    finally:
        conn.close()

def get_all_settings() -> dict:
    """取得所有設定 (回傳 dict)"""
    conn = get_db_connection()
    settings = {}
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT setting_key, setting_value FROM system_settings")
                rows = cursor.fetchall()
                for row in rows:
                    settings[row[0]] = row[1]
            except pymysql.err.ProgrammingError:
                pass
    finally:
        conn.close()
    return settings

def install_package(package_name: str) -> bool:
    """
    熱安裝指定的 Python 套件
    返回 True 表示安裝成功或已安裝，False 表示安裝失敗。
    """
    try:
        print(f"[Settings Manager] Installing package: {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"[Settings Manager] Successfully installed {package_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[Settings Manager] Failed to install {package_name}: {e}")
        return False

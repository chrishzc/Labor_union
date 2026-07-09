# -*- coding: utf-8 -*-
"""
File: admin/pages/0_setup.py
Description: 🔌 系統環境初始化 (Setup Mode) - 當資料庫未就緒時顯示。
"""
import streamlit as st
import os
import sys
import shutil
import pymysql
import dotenv

# 確保可以匯入 admin.utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from admin.utils import get_db_connection

st.set_page_config(
    page_title="系統環境初始化 - 月子工會系統",
    page_icon="🔌",
    layout="centered"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Outfit', 'Microsoft JhengHei', sans-serif; }
    .page-title {
        background: linear-gradient(135deg, #FF6B6B 0%, #C0392B 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">🔌 系統環境初始化</div>', unsafe_allow_html=True)
st.warning("⚠️ 系統偵測到資料庫無法連線，或是尚未建立設定檔。請填寫下方資訊以完成系統初始化。")

# 取得根目錄的 .env 路徑
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
env_example_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env.example"))

# 若沒有 .env，嘗試從 example 複製
if not os.path.exists(env_path):
    if os.path.exists(env_example_path):
        shutil.copyfile(env_example_path, env_path)
    else:
        # 如果連 example 都沒有，建一個空的
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# 月子公會系統 - 自動產生\n")
    dotenv.load_dotenv(env_path)

# 表單
with st.form("setup_form"):
    st.subheader("MySQL 資料庫連線設定")
    db_host = st.text_input("Host (主機位址)", value=os.getenv("DB_HOST", "127.0.0.1"))
    db_port = st.text_input("Port (通訊埠)", value=os.getenv("DB_PORT", "3306"))
    db_user = st.text_input("User (帳號)", value=os.getenv("DB_USER", "root"))
    db_pass = st.text_input("Password (密碼)", value=os.getenv("DB_PASSWORD", "1234"), type="password")
    db_name = st.text_input("Database (資料庫名稱)", value=os.getenv("DB_DATABASE", "union_db"))
    
    submitted = st.form_submit_button("💾 儲存並初始化資料庫")
    
    if submitted:
        with st.spinner("正在儲存設定並測試連線..."):
            # 寫入 .env
            dotenv.set_key(env_path, "DB_HOST", db_host)
            dotenv.set_key(env_path, "DB_PORT", db_port)
            dotenv.set_key(env_path, "DB_USER", db_user)
            dotenv.set_key(env_path, "DB_PASSWORD", db_pass)
            dotenv.set_key(env_path, "DB_DATABASE", db_name)
            
            # 為了讓當下的 python process 讀到，手動設定 os.environ
            os.environ["DB_HOST"] = db_host
            os.environ["DB_PORT"] = db_port
            os.environ["DB_USER"] = db_user
            os.environ["DB_PASSWORD"] = db_pass
            os.environ["DB_DATABASE"] = db_name
            
            # 測試連線與建庫
            try:
                # 第一階段：連接 MySQL server 確保資料庫存在
                conn_server = pymysql.connect(
                    host=db_host, port=int(db_port), user=db_user, password=db_pass, charset="utf8mb4"
                )
                with conn_server.cursor() as cursor:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                conn_server.commit()
                conn_server.close()
                
                # 第二階段：連接指定資料庫並建立 Table (讀取 schema.sql)
                conn = get_db_connection()
                schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "db", "schema.sql"))
                if os.path.exists(schema_path):
                    with open(schema_path, "r", encoding="utf-8") as f:
                        sql_script = f.read()
                    
                    with conn.cursor() as cursor:
                        # 簡單地根據分號切分執行
                        commands = sql_script.split(";")
                        for cmd in commands:
                            if cmd.strip():
                                try:
                                    cursor.execute(cmd)
                                except Exception as cmd_e:
                                    print(f"[Setup] Error executing sql: {cmd[:50]}... Error: {cmd_e}")
                    conn.commit()
                conn.close()
                
                st.success("✅ 資料庫連線測試成功，且 Table 建立完畢！請稍候，系統將自動重啟進入主畫面...")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 初始化失敗：{e}")
                st.info("請檢查帳號密碼是否正確，或是 MySQL 伺服器是否有啟動。")

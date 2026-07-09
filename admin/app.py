# -*- coding: utf-8 -*-
"""
File: admin/app.py
Description: 新竹市月子工會自動化管理系統 - 管理端 UI 導覽首頁 (主入口)
"""
import streamlit as st
import pymysql
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 設定頁面配置
st.set_page_config(
    page_title="新竹市月子工會自動化管理系統",
    page_icon="👶",
    layout="wide",
    initial_sidebar_state="expanded"
)

from utils import get_db_connection

# 偵測資料庫連線
def check_db_connection():
    try:
        conn = get_db_connection()
        conn.close()
        return True, "連線成功"
    except Exception as e:
        return False, str(e)

# 將首頁渲染邏輯封裝至函數中
def show_home():
    # 側邊欄狀態展示
    st.sidebar.markdown("### 🛠️ 系統整合狀態")
    db_ok, db_msg = check_db_connection()
    if db_ok:
        st.sidebar.success("🟢 MySQL 連線：正常")
    else:
        st.sidebar.error(f"🔴 MySQL 連線：失敗\n\n{db_msg}")
    st.sidebar.info("💡 請在左側選單切換至各功能模組進行操作。")

    # 自訂 CSS 樣式
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'Outfit', 'Microsoft JhengHei', sans-serif;
        }
        .main-title {
            background: linear-gradient(135deg, #3A7BD5 0%, #3A6073 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.8rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
            padding-top: 1rem;
        }
        .subtitle {
            color: #718096;
            font-size: 1.2rem;
            margin-bottom: 2rem;
        }
        .card-container {
            display: flex;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .feature-card {
            background: #F7FAFC;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            padding: 1.8rem;
            border-top: 4px solid #3A7BD5;
            flex: 1;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .feature-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            background: #FFFFFF;
        }
        .card-icon {
            font-size: 2rem;
            margin-bottom: 0.8rem;
        }
        .card-title {
            font-size: 1.3rem;
            font-weight: 600;
            color: #2D3748;
            margin-bottom: 0.5rem;
        }
        .card-text {
            color: #4A5568;
            font-size: 0.95rem;
            line-height: 1.5;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<h1 class="main-title">👶 月子工會行政與客服自動化系統</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">新竹市月子照顧服務人員職業工會 — 地端整合後台管理系統</p>', unsafe_allow_html=True)

    st.markdown("""
    ### 🚀 系統功能導覽
    請使用側邊欄的選單，進入以下四大核心模組：
    """)

    st.markdown("""
    <div class="card-container">
        <div class="feature-card">
            <div class="card-icon">📊</div>
            <div class="card-title">儀表板與異常處理</div>
            <div class="card-text">
                檢視今日核心業務指標，並可即時處理從 BeClass 或市府 Excel 匯入時產生的資料異常。行政人員可在此一鍵進行人工資料更正與隔離。
            </div>
        </div>
        <div class="feature-card">
            <div class="card-icon">📅</div>
            <div class="card-title">月嫂行事曆與排班</div>
            <div class="card-text">
                自動載入月嫂的週休偏好，依出勤天數與請假/休假狀況即時精算結束日，保障足額服務。月曆表網格配色動態呈現狀態。
            </div>
        </div>
        <div class="feature-card">
            <div class="card-icon">🤝</div>
            <div class="card-title">案件與配對中心</div>
            <div class="card-text">
                管理案件金流狀態與狀態推進。針對洽談中案件，提供篩選、意願詢問、履歷推播與線上合約簽署等四步媒合流程。
            </div>
        </div>
        <div class="feature-card">
            <div class="card-icon">📋</div>
            <div class="card-title">所需表格與週報</div>
            <div class="card-text">
                自動串接資料庫現有欄位，即時計算時數、補助款、各期款金額與付款日期。按週彙總生成市民/社福統計表，支援一鍵下載 Excel 報表。
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    ---
    ### ⚙️ 系統工作流程架構
    本自動化系統由 **地端資料庫容器化**、**自動監控 Pipeline (File Watcher)** 以及 **LINE 互動 API** 組成。
    下圖展示了行政人員下載 Excel 後，系統資料是如何在各層級進行自動化流轉與處理的：
    """)

    st.markdown("""
    ```mermaid
    graph TD
        A[1. 行政下載 Excel] -->|丟入 downloads/ 子目錄| B(2. File Watcher 偵測變更)
        B -->|3. 自動執行微匯入 Pipeline| C[(4. MySQL: union_db)]
        C -->|5. 讀取異常/排班/媒合/報表| D[5. Streamlit 管理後台]
        D -->|6. 手動修正 / 觸發媒合| C
        D -->|7. 發送 LINE 意願/履歷/合約| E(7. LINE 官方帳號 / 三方服務群組)
    ```
    """)

# 資料庫連線探針
def is_db_connected():
    try:
        conn = get_db_connection()
        conn.close()
        return True
    except Exception:
        return False

# 根據連線狀態動態切換導覽列
if not is_db_connected():
    pg = st.navigation([st.Page("pages/0_setup.py", title="🔌 系統環境初始化", default=True)])
else:
    pg = st.navigation({
        "系統選單": [
            st.Page(show_home, title="🏠 系統首頁", default=True)
        ],
        "核心模組": [
            st.Page("pages/1_dashboard.py", title="📊 儀表板與異常處理"),
            st.Page("pages/2_calendar.py", title="📅 月嫂行事曆與排班"),
            st.Page("pages/3_matching.py", title="🤝 案件與配對中心"),
            st.Page("pages/4_report.py", title="📋 所需表格與週報")
        ],
        "系統管理": [
            st.Page("pages/5_knowledge_base.py", title="📚 知識庫維護中心"),
            st.Page("pages/9_settings.py", title="⚙️ 系統全域設定")
        ]
    })

pg.run()

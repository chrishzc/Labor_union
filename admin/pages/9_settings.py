# -*- coding: utf-8 -*-
"""
File: admin/pages/9_settings.py
Description: 頁面九：⚙️ 系統全域設定 (System Settings)
"""
import streamlit as st
import os
import sys

# 動態設定 sys.path 確保能定位到 admin.utils 與 admin.settings_manager
if "." not in sys.path:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from admin.settings_manager import get_setting, set_setting, install_package

st.set_page_config(
    page_title="系統全域設定 - 月子工會系統",
    page_icon="⚙️",
    layout="wide"
)

# 嵌入客製化 CSS 樣式
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Microsoft JhengHei', sans-serif;
    }
    
    .page-title {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
    
    .setting-card {
        background: #FFFFFF;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        padding: 2rem;
        margin-bottom: 2rem;
        border-left: 5px solid #667eea;
    }
    
    .setting-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #2D3748;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .stButton > button {
        background-color: #667eea !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        padding: 0.5rem 2rem !important;
        border: none !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover {
        background-color: #764ba2 !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">⚙️ 系統全域設定 (System Settings)</div>', unsafe_allow_html=True)
st.markdown("在此集中管理系統底層的運作模式，包含人工智慧模型與 LINE 官方介接機制的動態切換。修改後將即時套用於後端背景服務中。")

# 讀取現有設定
current_embedding_mode = get_setting("embedding_mode", "default")
current_openai_key = get_setting("openai_api_key", "")
current_line_reply_mode = get_setting("line_reply_mode", "push_daemon")
current_line_token = get_setting("line_channel_access_token", "")
current_line_secret = get_setting("line_channel_secret", "")

# ---------- 區塊一：AI 與 RAG 知識庫模型設定 ----------
st.markdown('<div class="setting-card">', unsafe_allow_html=True)
st.markdown('<div class="setting-header">🧠 AI 與 RAG 知識庫模型設定</div>', unsafe_allow_html=True)
st.markdown("設定自動回覆系統在進行語意檢索 (Embedding) 時所使用的引擎。")

embedding_options = {
    "default": "選項 3: ChromaDB 內建英式模型 (效能最佳、不需外部套件、中文極差)",
    "openai": "選項 1: 雲端 API - OpenAI text-embedding-3-small (推薦！精準且不吃地端效能)",
    "local": "選項 2: 地端開源中文模型 - text2vec-base-chinese (需安裝套件、吃伺服器記憶體)"
}
# 找到目前的 index
embedding_keys = list(embedding_options.keys())
try:
    default_idx = embedding_keys.index(current_embedding_mode)
except ValueError:
    default_idx = 0

selected_embedding_desc = st.selectbox(
    "請選擇 Embedding (向量化) 模型來源：", 
    options=list(embedding_options.values()),
    index=default_idx
)
# 反推 key
selected_embedding_key = next(k for k, v in embedding_options.items() if v == selected_embedding_desc)

input_openai_key = current_openai_key
if selected_embedding_key == "openai":
    st.info("💡 提示：使用 OpenAI Embedding API 成本極低，僅進行語句向量化，不會有 LLM 幻覺產生。")
    input_openai_key = st.text_input("請輸入您的 OpenAI API Key (sk-...)：", value=current_openai_key, type="password")
elif selected_embedding_key == "local":
    st.warning("⚠️ 警告：啟用此選項將於背景下載近 1GB 的開源中文模型，可能會造成首次啟動卡頓。")

if st.button("💾 儲存並套用模型設定", key="save_ai"):
    with st.spinner("正在儲存設定與檢查套件相依性..."):
        success = True
        if selected_embedding_key == "openai":
            if not input_openai_key:
                st.error("請輸入 OpenAI API Key！")
                success = False
            else:
                if install_package("openai"):
                    set_setting("openai_api_key", input_openai_key, "OpenAI API Key")
                else:
                    success = False
                    st.error("套件 openai 安裝失敗！")
        elif selected_embedding_key == "local":
            if install_package("sentence-transformers"):
                pass
            else:
                success = False
                st.error("套件 sentence-transformers 安裝失敗！")
                
        if success:
            set_setting("embedding_mode", selected_embedding_key, "RAG 向量模型模式")
            st.success("✅ AI 模型設定已儲存並啟用。")
st.markdown('</div>', unsafe_allow_html=True)


# ---------- 區塊二：LINE 介接模式設定 ----------
st.markdown('<div class="setting-card">', unsafe_allow_html=True)
st.markdown('<div class="setting-header">💬 LINE 介接與回覆模式</div>', unsafe_allow_html=True)
st.markdown("設定系統如何發送自動回覆或通知給使用者。")

line_options = {
    "push_daemon": "模式 2: 背景排程推播 (預設，將訊息排入佇列由 Daemon 發送 Push Message)",
    "reply_sdk": "模式 1: SDK 即時回覆 (推薦，免推播費，使用 Reply API 即時回應)"
}
line_keys = list(line_options.keys())
try:
    line_default_idx = line_keys.index(current_line_reply_mode)
except ValueError:
    line_default_idx = 0

selected_line_desc = st.radio(
    "請選擇 LINE 訊息回覆機制：",
    options=list(line_options.values()),
    index=line_default_idx
)
selected_line_key = next(k for k, v in line_options.items() if v == selected_line_desc)

input_line_token = current_line_token
input_line_secret = current_line_secret
if selected_line_key == "reply_sdk":
    st.info("💡 提示：使用 Reply SDK 需填寫 Channel Access Token 與 Channel Secret。")
    col1, col2 = st.columns(2)
    with col1:
        input_line_token = st.text_input("Channel Access Token", value=current_line_token, type="password")
    with col2:
        input_line_secret = st.text_input("Channel Secret", value=current_line_secret, type="password")

if st.button("💾 儲存並套用 LINE 設定", key="save_line"):
    with st.spinner("正在儲存設定與檢查套件相依性..."):
        success = True
        if selected_line_key == "reply_sdk":
            if not input_line_token or not input_line_secret:
                st.error("請完整填寫 Channel Access Token 與 Secret！")
                success = False
            else:
                if install_package("line-bot-sdk"):
                    set_setting("line_channel_access_token", input_line_token, "LINE Access Token")
                    set_setting("line_channel_secret", input_line_secret, "LINE Channel Secret")
                else:
                    success = False
                    st.error("套件 line-bot-sdk 安裝失敗！")
                    
        if success:
            set_setting("line_reply_mode", selected_line_key, "LINE 回覆模式")
            st.success("✅ LINE 設定已儲存並啟用。")
st.markdown('</div>', unsafe_allow_html=True)

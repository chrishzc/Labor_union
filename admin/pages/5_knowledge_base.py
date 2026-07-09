# -*- coding: utf-8 -*-
"""
File: admin/pages/5_knowledge_base.py
Description: 頁面五：📚 知識庫維護中心 (FAQ Management)
"""
import streamlit as st
import os
import sys
import pandas as pd
import chromadb

# 動態設定 sys.path 確保能定位到 admin.utils
if "." not in sys.path:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from admin.utils import get_db_connection
from admin.settings_manager import get_setting

st.set_page_config(
    page_title="知識庫維護中心 - 月子工會系統",
    page_icon="📚",
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
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.3rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">📚 知識庫維護中心 (FAQ Management)</div>', unsafe_allow_html=True)
st.markdown("在這裡新增或編輯知識庫問答。新增的內容將會同步存入關聯式資料庫備份，並進行語意向量化寫入 ChromaDB 以供 RAG 自動回覆系統使用。")

# --- 取得 ChromaDB Collection 實例 ---
@st.cache_resource
def get_chroma_collection():
    mode = get_setting("embedding_mode", "default")
    embedding_function = None
    
    try:
        if mode == "openai":
            import chromadb.utils.embedding_functions as embedding_functions
            api_key = get_setting("openai_api_key", "")
            if api_key:
                embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=api_key,
                    model_name="text-embedding-3-small"
                )
            else:
                st.warning("⚠️ 尚未設定 OpenAI API Key，回退為預設模型。")
        elif mode == "local":
            import chromadb.utils.embedding_functions as embedding_functions
            embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="shibing624/text2vec-base-chinese"
            )
    except ImportError:
        st.warning("⚠️ 找不到對應的 Embedding 套件，已回退為 ChromaDB 預設模型。請至系統設定安裝套件。")
        
    client = chromadb.PersistentClient(path="./db/chroma_data")
    if embedding_function:
        collection = client.get_or_create_collection(
            name="union_faq", 
            embedding_function=embedding_function
        )
    else:
        collection = client.get_or_create_collection(name="union_faq")
    
    return collection

try:
    collection = get_chroma_collection()
except Exception as e:
    st.error(f"ChromaDB 載入失敗: {e}")
    collection = None

# --- 新增問答區塊 ---
st.subheader("➕ 新增問答")
with st.form("add_faq_form"):
    col1, col2 = st.columns([1, 4])
    with col1:
        category = st.selectbox("分類標籤", ["一般", "業務規章", "繳款問題", "排班規定", "其他"])
    with col2:
        question = st.text_input("問題 (Question):", placeholder="例如：月嫂的服務費用怎麼計算？")
    
    answer = st.text_area("標準答案 (Answer):", placeholder="此為 RAG 回覆給使用者的預設回答，請填寫完整官方答覆。")
    
    submitted = st.form_submit_button("儲存並向量化 (Save & Embed)")
    if submitted:
        if not question or not answer:
            st.error("問題與答案不可為空！")
        else:
            with st.spinner("正在寫入資料庫並進行語意向量化..."):
                conn = get_db_connection()
                try:
                    with conn.cursor() as cursor:
                        # 1. 寫入 MySQL
                        cursor.execute("""
                            INSERT INTO knowledge_faq (question, answer, category)
                            VALUES (%s, %s, %s)
                        """, (question, answer, category))
                        faq_id = cursor.lastrowid
                        conn.commit()
                        
                        # 2. Upsert 至 ChromaDB
                        if collection:
                            collection.upsert(
                                documents=[question],
                                metadatas=[{"answer": answer, "category": category}],
                                ids=[str(faq_id)]
                            )
                        st.success(f"✅ 成功新增問答 #{faq_id}，已同步至 RAG 向量資料庫。")
                except Exception as e:
                    conn.rollback()
                    st.error(f"儲存失敗：{e}")
                finally:
                    conn.close()

# --- 瀏覽現有知識庫 ---
st.divider()
st.subheader("📋 現有知識庫列表")
try:
    conn = get_db_connection()
    df = pd.read_sql("SELECT id as ID, category as 分類, question as 問題, answer as 解答, created_at as 建立時間 FROM knowledge_faq ORDER BY id DESC", conn)
    conn.close()
    
    if df.empty:
        st.info("目前知識庫尚未有資料。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"載入知識庫列表失敗: {e}")

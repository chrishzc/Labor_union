import streamlit as st
import os
import importlib
import sys

import requests

# 將專案根目錄加入 Python 搜尋路徑，以利讀取 services
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from ui.nav_helper import NAV_KEY, apply_pending_navigation, request_tab
from ui.pages import shared as ui_shared
from services.form_agent_service import run_form_agent
from services.qa_agent_service import run_qa_agent

st.set_page_config(page_title="Lobar Union 管理系統", layout="wide")

AI_ASSISTANT_MODE_KEY = "ai_assistant_mode"
AI_ASSISTANT_PROPOSAL_KEY = "ai_assistant_proposal"
AI_ASSISTANT_HISTORY_KEY = "ai_assistant_history"
AI_ASSISTANT_QA_HISTORY_KEY = "ai_assistant_qa_history"
MODE_QA = "💬 問答"
MODE_FORM = "✏️ 修改表單"


def _render_ai_assistant_fab():
    """全站右上角浮動的 AI 助理圖示；在 ui/app.py 這個唯一的全域進入點注入一次，
    所有頁面都看得到，不需要在每個 ui/pages/*.py 裡各自重複。"""
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"] > div.st-key-ai_assistant_fab {
            position: fixed;
            top: 0.55rem;
            right: 5rem;
            z-index: 9999;
        }
        .st-key-ai_assistant_fab button {
            border-radius: 50%;
            width: 2.3rem;
            height: 2.3rem;
            padding: 0;
            overflow: visible;
        }
        .st-key-ai_assistant_fab button p {
            transform: scale(2.6);
            line-height: 1;
            margin: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="ai_assistant_fab"):
        if st.button("🤖", key="ai_assistant_fab_button", help="AI 助理"):
            _ai_assistant_dialog()


@st.dialog("🤖 AI 助理")
def _ai_assistant_dialog():
    mode = st.segmented_control(
        "模式",
        [MODE_QA, MODE_FORM],
        default=st.session_state.get(AI_ASSISTANT_MODE_KEY, MODE_QA),
        key=AI_ASSISTANT_MODE_KEY,
        label_visibility="collapsed",
    )

    if mode == MODE_QA:
        _render_qa_mode()
    else:
        _render_form_mode()


def _render_qa_mode():
    st.caption(
        "問案件查詢（例如「案號 115000001 的狀態」）或系統操作問題（例如「行事曆的休假怎麼安排」）。"
        "只回答查詢類問題，不會修改任何資料。"
    )

    for role, content in st.session_state.get(AI_ASSISTANT_QA_HISTORY_KEY, []):
        with st.chat_message(role):
            st.markdown(content)

    user_input = st.chat_input("輸入你想查詢的內容...", key="ai_assistant_qa_input")
    if user_input:
        # 先取「這次提問之前」的歷史再傳給 agent，讓它知道上一輪聊了什麼
        # （例如助理剛反問「要調整哪個頁面」，使用者這次只回一個詞，agent 才看得懂在回答什麼）。
        prior_history = list(st.session_state.get(AI_ASSISTANT_QA_HISTORY_KEY, []))
        st.session_state.setdefault(AI_ASSISTANT_QA_HISTORY_KEY, []).append(("user", user_input))
        with st.spinner("AI 正在查詢..."):
            result = run_qa_agent(user_input, history=prior_history)
        st.session_state.setdefault(AI_ASSISTANT_QA_HISTORY_KEY, []).append(
            ("assistant", result.get("message") or "（沒有回應）")
        )
        st.rerun(scope="fragment")


def _render_form_mode():
    st.caption(
        "用自然語言描述你想修改的欄位，例如：「幫我把案號 115000001 的電話改成 0912345678」。"
        "AI 只會提出建議，實際寫入資料庫需要你在下方確認。"
    )

    for role, content in st.session_state.get(AI_ASSISTANT_HISTORY_KEY, []):
        with st.chat_message(role):
            st.markdown(content)

    proposal = st.session_state.get(AI_ASSISTANT_PROPOSAL_KEY)
    if proposal and proposal.get("status") == "pending_confirmation":
        st.markdown("---")
        st.markdown(
            f"**資料表**: `{proposal['table']}`　**欄位**: `{proposal['field_name']}`"
        )
        col_old, col_new = st.columns(2)
        with col_old:
            st.metric("目前值", proposal.get("old_value") or "（空白）")
        with col_new:
            st.metric("新值", proposal.get("new_value"))

        confirmed = st.checkbox("我已確認以上異動內容無誤", key="ai_assistant_confirm_checkbox")
        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.button("✅ 套用變更", type="primary", disabled=not confirmed, key="ai_assistant_apply_btn"):
                try:
                    resp = requests.patch(
                        f"{ui_shared.resolve_api_base_url()}/api/v1/admin/data-browser/"
                        f"{proposal['table']}/{proposal['row_id']}",
                        headers=ui_shared.build_admin_headers(),
                        json={"updates": {proposal["field_name"]: proposal["new_value"]}},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    st.session_state[AI_ASSISTANT_PROPOSAL_KEY] = None
                    st.session_state.setdefault(AI_ASSISTANT_HISTORY_KEY, []).append(
                        ("assistant", "✅ 已成功套用變更並寫入稽核紀錄。")
                    )
                    st.rerun(scope="fragment")
                except Exception as e:
                    st.error(f"套用失敗: {e}")
        with col_cancel:
            if st.button("取消此建議", key="ai_assistant_cancel_btn"):
                st.session_state[AI_ASSISTANT_PROPOSAL_KEY] = None
                st.rerun(scope="fragment")

    user_input = st.chat_input("輸入你想修改的內容...")
    if user_input:
        st.session_state.setdefault(AI_ASSISTANT_HISTORY_KEY, []).append(("user", user_input))
        with st.spinner("AI 正在分析..."):
            result = run_form_agent(user_input)

        if result.get("status") == "pending_confirmation":
            st.session_state[AI_ASSISTANT_PROPOSAL_KEY] = result
            st.session_state.setdefault(AI_ASSISTANT_HISTORY_KEY, []).append((
                "assistant",
                f"我建議把 `{result['table']}` 資料表的 `{result['field_name']}` 欄位"
                f"改成 `{result['new_value']}`，請在下方確認。",
            ))
        else:
            st.session_state[AI_ASSISTANT_PROPOSAL_KEY] = None
            st.session_state.setdefault(AI_ASSISTANT_HISTORY_KEY, []).append(
                ("assistant", result.get("message") or "（沒有回應）")
            )
        st.rerun(scope="fragment")

# AI 助理回答裡的頁面連結用 ?page=xxx 這個網址參數導覽，不能直接連到 Streamlit 原生偵測到的
# /xxx 路由——這個 App 用自訂的 st.sidebar.radio + NAV_KEY 機制切換頁面（見 ui/nav_helper.py），
# 頁面檔案本身刻意不含頂層 show() 呼叫，所以透過 Streamlit 原生路由直接開啟該頁檔案時畫面會是空的。
PAGE_SLUG_TO_TITLE = {
    "data_browser": "🔍 資料庫原始資料瀏覽",
    "orders": "📦 訂單與帳務管理系統",
    "calendar": "📅 服務人員行事曆與休假安排",
    "form_management": "📋 表單與履歷問卷管理",
    "finance_alerts": "🚨 異常警示中心",
    "line_management": "💬 LINE 管理中心",
}


def _apply_page_query_param(page_titles: list[str]) -> None:
    """把 ?page=xxx 網址參數對應到側邊欄頁面標題並切換過去；用完就清掉，
    避免使用者之後手動切換頁面、重新整理瀏覽器時又被拉回這頁。
    如果同時帶了 ?tab=xxx（AI 助理答覆裡指到某頁面下specific分頁的深連結），
    也一併存成 pending tab 提示，交給該頁面自己的殼層（例如
    ui/pages/02_orders.py）在渲染時決定要不要跳過分頁列、直接顯示該分頁。"""
    page_slug = st.query_params.get("page")
    if not page_slug:
        return
    title = PAGE_SLUG_TO_TITLE.get(page_slug)
    if title in page_titles:
        st.session_state[NAV_KEY] = title
        tab_slug = st.query_params.get("tab")
        if tab_slug:
            request_tab(tab_slug)
    st.query_params.clear()


# 鎖定在同目錄下的 pages 資料夾
PAGES_DIR = os.path.join(CURRENT_DIR, "pages")

def load_pages():
    pages = {}
    if os.path.exists(PAGES_DIR):
        for file in sorted(os.listdir(PAGES_DIR)):
            if file.endswith(".py") and not file.startswith("_"):
                module_name = file[:-3]
                try:
                    full_module_name = f"ui.pages.{module_name}"
                    # 如果已經加載過該模組，使用 reload 強制刷新記憶體快取，對齊硬碟最新程式碼
                    if full_module_name in sys.modules:
                        mod = importlib.reload(sys.modules[full_module_name])
                    else:
                        mod = importlib.import_module(full_module_name)
                        
                    if hasattr(mod, "title") and hasattr(mod, "show"):
                        pages[mod.title] = mod.show
                except Exception as e:
                    st.sidebar.error(f"載入頁面 {file} 失敗: {e}")
    return pages

def main():
    _render_ai_assistant_fab()

    st.sidebar.title("🧭 Lobar Union 系統導覽")
    pages = load_pages()
    
    if not pages:
        st.warning("請在 `ui/pages/` 目錄下新增頁面模組。")
        return
        
    page_titles = list(pages.keys())
    apply_pending_navigation()
    _apply_page_query_param(page_titles)
    if NAV_KEY not in st.session_state or st.session_state[NAV_KEY] not in page_titles:
        st.session_state[NAV_KEY] = page_titles[0]
    choice = st.sidebar.radio("前往頁面", page_titles, key=NAV_KEY)

    # 執行該分頁的 show()
    pages[choice]()

if __name__ == "__main__":
    main()

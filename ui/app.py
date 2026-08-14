import streamlit as st
import importlib
import os
import sys
from collections.abc import Mapping

# 將專案根目錄加入 Python 搜尋路徑，以利讀取 services
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from ui.nav_helper import NAV_KEY, apply_pending_navigation

st.set_page_config(page_title="Lobar Union 管理系統", layout="wide")

DEFAULT_PAGE_TITLE = "📦 訂單管理"
NAV_SECTION_KEY = "nav_section"
PAGE_REGISTRY: Mapping[str, tuple[tuple[str, str], ...]] = {
    "營運作業": (
        ("📦 訂單管理", "ui.pages.02_orders"),
        ("多月嫂排班", "ui.pages.03_calendar"),
        ("📋 表單與履歷問卷管理", "ui.pages.05_form_management"),
        ("💬 LINE 管理中心", "ui.pages.07_line_management"),
    ),
    "帳務": (
        ("💰 帳務作業中心", "ui.pages.04_finance"),
    ),
    "異常與稽核": (
        ("異常警示中心", "ui.pages.06_finance_alerts"),
        ("🔍 資料庫原始資料瀏覽", "ui.pages.01_data_browser"),
        ("工會人員權限", "ui.pages.09_access_management"),
        ("🩺 系統狀態", "ui.pages.08_system_status"),
    ),
}


def _load_page_show(module_name):
    module = importlib.import_module(module_name)
    show = getattr(module, "show", None)
    if not callable(show):
        raise TypeError(f"{module_name} 缺少可呼叫的 show()")
    return show


# Kept cohesive because selection and lazy page execution form one shell boundary.
def main():
    st.sidebar.title("🧭 Lobar Union 系統導覽")
    apply_pending_navigation()
    pages = _page_modules(PAGE_REGISTRY)
    page_titles = tuple(pages)
    if NAV_KEY not in st.session_state or st.session_state[NAV_KEY] not in page_titles:
        st.session_state[NAV_KEY] = DEFAULT_PAGE_TITLE
    _apply_navigation_section(st.session_state[NAV_KEY])
    section = st.sidebar.selectbox(
        "功能分類",
        tuple(PAGE_REGISTRY),
        key=NAV_SECTION_KEY,
        on_change=_select_first_page_in_section,
    )
    section_pages = PAGE_REGISTRY[section]
    choice = st.sidebar.radio(
        "前往頁面",
        tuple(title for title, _ in section_pages),
        key=NAV_KEY,
    )

    # 執行該分頁的 show()
    try:
        show = _load_page_show(pages[choice])
    except Exception as error:
        st.error(f"載入頁面失敗：{error}")
        return
    show()


def _page_modules(
    registry: Mapping[str, tuple[tuple[str, str], ...]],
) -> dict[str, str]:
    return {
        title: module_name
        for pages in registry.values()
        for title, module_name in pages
    }


def _apply_navigation_section(page_title: str) -> None:
    for section, pages in PAGE_REGISTRY.items():
        if page_title in {title for title, _ in pages}:
            st.session_state[NAV_SECTION_KEY] = section
            return
    st.session_state[NAV_KEY] = DEFAULT_PAGE_TITLE
    st.session_state[NAV_SECTION_KEY] = _section_for(DEFAULT_PAGE_TITLE)


def _select_first_page_in_section() -> None:
    section = st.session_state[NAV_SECTION_KEY]
    st.session_state[NAV_KEY] = PAGE_REGISTRY[section][0][0]


def _section_for(page_title: str) -> str:
    return next(
        section
        for section, pages in PAGE_REGISTRY.items()
        if page_title in {title for title, _ in pages}
    )

if __name__ == "__main__":
    main()

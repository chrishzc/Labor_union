import streamlit as st
import ast
import os
import importlib
import sys

# 將專案根目錄加入 Python 搜尋路徑，以利讀取 services
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from ui.nav_helper import NAV_KEY, apply_pending_navigation

st.set_page_config(page_title="Lobar Union 管理系統", layout="wide")

# 鎖定在同目錄下的 pages 資料夾
PAGES_DIR = os.path.join(CURRENT_DIR, "pages")
DEFAULT_PAGE_TITLE = "📦 訂單與帳務管理系統"


def load_pages():
    pages = {}
    if os.path.exists(PAGES_DIR):
        for file in sorted(os.listdir(PAGES_DIR)):
            if file.endswith(".py") and not file.startswith("_"):
                try:
                    title = _page_title(os.path.join(PAGES_DIR, file))
                    if title:
                        pages[title] = f"ui.pages.{file[:-3]}"
                except Exception as e:
                    st.sidebar.error(f"載入頁面 {file} 失敗: {e}")
    return pages


def _page_title(path):
    with open(path, encoding="utf-8", errors="strict") as source:
        tree = ast.parse(source.read(), filename=path)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        if isinstance(target, ast.Name) and target.id == "title":
            return ast.literal_eval(node.value)
    return None


def _load_page_show(module_name):
    module = importlib.import_module(module_name)
    show = getattr(module, "show", None)
    if not callable(show):
        raise TypeError(f"{module_name} 缺少可呼叫的 show()")
    return show


# Kept cohesive because selection and lazy page execution form one shell boundary.
def main():
    st.sidebar.title("🧭 Lobar Union 系統導覽")
    pages = load_pages()
    
    if not pages:
        st.warning("請在 `ui/pages/` 目錄下新增頁面模組。")
        return
        
    page_titles = list(pages.keys())
    apply_pending_navigation()
    if NAV_KEY not in st.session_state or st.session_state[NAV_KEY] not in page_titles:
        st.session_state[NAV_KEY] = (
            DEFAULT_PAGE_TITLE
            if DEFAULT_PAGE_TITLE in pages
            else page_titles[0]
        )
    choice = st.sidebar.radio("前往頁面", page_titles, key=NAV_KEY)

    # 執行該分頁的 show()
    try:
        show = _load_page_show(pages[choice])
    except Exception as error:
        st.error(f"載入頁面失敗：{error}")
        return
    show()

if __name__ == "__main__":
    main()

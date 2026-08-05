# -*- coding: utf-8 -*-
"""
================================================================================
檔案名稱: scripts/build_help_index.py
功能說明: 從實際 Streamlit 頁面原始碼（module docstring + st.caption/st.info 說明文字）
         建立 chromadb 向量索引，供 services/mcp_form_tools.py::search_help 使用。
         刻意只抽取「使用者看得到的說明文字」，不是全文掃描——來源精準比對外文件
         更貼近目前真正上線的功能，且不需要額外的 embedding 模型（用 chromadb 內建
         的預設 embedder）。
用法: uv run python scripts/build_help_index.py
================================================================================
"""
import ast
import sys
from pathlib import Path

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.ollama_embedding import OllamaEmbeddingFunction  # noqa: E402
CHROMA_PERSIST_PATH = str(PROJECT_ROOT / "db" / "chroma_data")
COLLECTION_NAME = "web_admin_help_index"

# 人工挑選的來源檔案白名單：說明文字密度高、內容準確、非開發者專用術語。
# 涵蓋訂單流程全部 5 個分頁 (tab1~tab5)，避免像「月嫂配對」這種核心流程的頁面被漏掉。
SOURCE_FILES = [
    "ui/pages/03_calendar.py",
    "ui/pages/06_finance_alerts.py",
    "ui/pages/01_data_browser.py",
    "ui/pages/order/editor.py",
    "ui/pages/order/tab1_overview.py",
    "ui/pages/order/tab2_assign.py",
    "ui/pages/order/tab3_finance.py",
    "ui/pages/order/tab4_accounts_payable.py",
]

# 手動整理的導覽地圖：caption/docstring 抽取不到「側邊欄選單完整名稱 -> 裡面有哪些分頁」
# 這種跨檔案的結構資訊 (側邊欄標題定義在 ui/pages/0X_*.py 的 title 變數，分頁卻在子模組裡)。
# 直接用側邊欄與 st.tabs 的精確文字，讓 AI 回答「要去哪裡找 X」時能準確引用完整名稱，
# 不會只答「訂單頁面」這種找不到對應側邊欄項目的片段。
#
# 網址故意不寫進描述文字裡（不寫「（網址 /orders）」這種括號），只放在獨立的 url 欄位、
# 存進 chromadb metadata：LLM 回答時只會複誦「看得到的文字」，如果網址混在描述句子裡，
# 使用者會同時看到「文字裡的路徑」跟「answer 結尾自動補的可點擊連結」兩份重複資訊。
# url 只給 services/qa_agent_service.py::_extract_nav_target 讀取、組成連結，不會出現在答案正文裡。
#
# 第 4 個欄位 tab（選填，預設 None）：給頁面內還有多個 st.tabs 分頁、且該分頁值得
# 單獨深連結的情境用（Streamlit 的 st.tabs 沒辦法用程式切換分頁，只導到頁面本身
# 還是會停在第一個分頁）。實際消費見 ui/pages/02_orders.py::_render_order_page_shell。
NAVIGATION_MAP = [
    (
        "訂單導覽",
        "在側邊欄選「📦 訂單與帳務管理系統」，裡面有 5 個分頁：📊 訂單資訊總覽、"
        "🤝 月嫂配對中心（配對/指派月嫂在這裡）、💰 訂單帳務總覽、📤 應付帳款查詢/輸出、核銷補助清冊。",
        "/orders",
        None,
    ),
    (
        "應付帳款導覽",
        "應付帳款查詢/輸出在「📦 訂單與帳務管理系統」頁面裡的「📤 應付帳款查詢/輸出」分頁，"
        "可以查詢與下載應付帳款清單，這裡僅供查詢與下載，不會把任何帳款標記為已付款、已退款或已提交。",
        "/orders",
        "accounts_payable",
    ),
    (
        "行事曆導覽",
        "在側邊欄選「📅 服務人員行事曆與休假安排」可以安排休假、查看月曆與國定假日排班。"
        "這裡是排班/請假用的月曆畫面，不是查看服務人員基本資料（姓名、電話等）的地方，"
        "服務人員基本資料要去「🔍 資料庫原始資料瀏覽」查。",
        "/calendar",
        None,
    ),
    (
        "異常警示中心導覽",
        "在側邊欄選「🚨 異常警示中心」，裡面分兩組分頁：訂單/帳務類（🤝 訂單配對、📝 待補資料、"
        "📤 補發送資訊、💸 帳務逾期提醒）與行事曆類（📅 行事曆、💰 帳務拆分確認、⏳ 待回覆接案意願）。",
        "/finance_alerts",
        None,
    ),
    (
        "表單管理導覽",
        "在側邊欄選「📋 表單與履歷問卷管理」，裡面有 3 個分頁：➕ 手動創建與設計新表單、"
        "🗄️ 自訂表單模板庫、📜 制式定型化契約管理。",
        "/form_management",
        None,
    ),
    (
        "資料庫瀏覽導覽",
        "在側邊欄選「🔍 資料庫原始資料瀏覽」，進入後在畫面上方"
        "「選擇要瀏覽的資料表」下拉選單裡選擇要查看的資料表，可以直接瀏覽/編輯各資料表的原始內容。"
        "要查服務人員/月嫂的基本資料（姓名、電話等）請選「服務人員/月嫂名冊 (staff)」；"
        "要查客戶的基本資料請選「客戶名冊 (clients)」；要查訂單資料請選「訂單資料 (orders)」。"
        "要查服務人員或客戶的基本資料（不是排班/請假）就是來這裡。",
        "/data_browser",
        None,
    ),
    (
        "LINE管理導覽",
        "在側邊欄選「💬 LINE 管理中心」管理 LINE 推播與訊息相關功能。",
        "/line_management",
        None,
    ),
]


def _extract_caption_texts(tree: ast.Module) -> list[str]:
    """找出所有 st.caption/st.info/st.subheader/st.header/st.title 呼叫的第一個字串常數參數。
    subheader/header/title 通常是「這個分頁/區塊叫什麼、是做什麼的」，
    對「要去哪裡找某功能」這類導覽問題特別有用，caption/info 則多半是操作細節/狀態提示。"""
    texts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in ("caption", "info", "subheader", "header", "title")
        ):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "st"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            text = first_arg.value.strip()
            if text:
                texts.append(text)
    return texts


# 專案裡每個檔案開頭都有一份「檔案名稱:.../功能說明:...」的樣板 docstring，
# 純粹是給開發者看的簡短標頭（通常 4 行、200~260 字元），不是給使用者看的說明，
# 混進索引反而會稀釋掉真正有結構性內容的 docstring (例如 03_calendar.py 有 900+ 字元、
# 06_finance_alerts.py 有 1900+ 字元的完整流程說明)。低於此門檻的一律視為樣板、不索引。
MIN_DOCSTRING_LENGTH = 400


def extract_chunks(file_path: Path) -> list[tuple[str, str]]:
    """回傳 [(chunk_id_suffix, text), ...]。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    chunks = []
    docstring = ast.get_docstring(tree)
    if docstring and len(docstring.strip()) >= MIN_DOCSTRING_LENGTH:
        chunks.append(("docstring", docstring.strip()))

    for i, text in enumerate(_extract_caption_texts(tree)):
        chunks.append((f"caption_{i}", text))

    return chunks


def main():
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)
    client.delete_collection(COLLECTION_NAME) if COLLECTION_NAME in [
        c.name for c in client.list_collections()
    ] else None
    collection = client.get_or_create_collection(
        COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction()
    )

    documents = []
    ids = []
    metadatas = []

    for rel_path in SOURCE_FILES:
        file_path = PROJECT_ROOT / rel_path
        if not file_path.exists():
            print(f"[SKIP] 找不到檔案: {rel_path}")
            continue
        for suffix, text in extract_chunks(file_path):
            documents.append(text)
            ids.append(f"{rel_path}::{suffix}")
            metadatas.append({"source": rel_path})

    for name, text, url, tab in NAVIGATION_MAP:
        documents.append(text)
        ids.append(f"navigation_map::{name}")
        metadata = {"source": "navigation_map", "url": url}
        if tab:
            metadata["tab"] = tab
        metadatas.append(metadata)

    if not documents:
        print("[WARN] 沒有抽取到任何內容，索引為空。")
        return

    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"[OK] 已建立索引 collection='{COLLECTION_NAME}'，共 {len(documents)} 筆內容。")
    print(f"  - navigation_map: {len(NAVIGATION_MAP)} 筆")
    for rel_path in SOURCE_FILES:
        count = sum(1 for i in ids if i.startswith(f"{rel_path}::"))
        print(f"  - {rel_path}: {count} 筆")


if __name__ == "__main__":
    main()

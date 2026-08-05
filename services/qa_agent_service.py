"""
================================================================================
檔案名稱: services/qa_agent_service.py
功能說明: 地端 LLM（Ollama, qwen2.5-coder:7b）驅動的查詢問答助理服務。
         只處理兩類唯讀查詢：案件基本資料查詢、網站操作方式問答；透過 MCP Client
         呼叫 services/mcp_form_tools.py 的 search_case_records/search_help 兩個
         唯讀工具。此服務完全不涉及資料寫入，跟 services/form_agent_service.py
         （表單修改建議）刻意分開，避免同一顆模型/同一個工具集合裡混雜「查詢」與
         「修改」兩種風險等級不同的操作。
================================================================================
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from services.form_agent_service import _extract_tool_call, run_with_retry

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_QA_AGENT_MODEL = os.getenv("OLLAMA_QA_AGENT_MODEL", "qwen2.5-coder:7b")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
MCP_ENDPOINT_URL = f"{API_BASE_URL}/mcp-tools/mcp"
# Streamlit UI 本身的網址（跟 API_BASE_URL 是不同的服務/port），用來把回答裡的頁面連結
# 組成完整可點擊的 http 網址，而不是只給相對路徑。
UI_BASE_URL = os.getenv("UI_BASE_URL", "http://localhost:8501").rstrip("/")
MAX_TOOL_ITERATIONS = 4

QA_TOOL_NAMES = {"search_case_records", "search_help"}

# 對應 scripts/build_help_index.py::NAVIGATION_MAP 裡實際存在的頁面路徑。
VALID_PAGE_PATHS = {
    "/orders", "/calendar", "/finance_alerts",
    "/form_management", "/data_browser", "/line_management",
}

SYSTEM_PROMPT = (
    "你是 Lobar Union 系統的查詢問答助理。你只能回答兩類問題：\n"
    "1) 案件查詢：用 search_case_records 工具查案號、姓名、電話、訂單狀態。"
    "呼叫時 keyword 參數只放具體的案號數字/姓名/電話本身，不要包含「案號」「姓名是」這類描述詞。\n"
    "2) 網站操作問答：用 search_help 工具查這個系統的頁面功能怎麼用。呼叫時 question 參數"
    "請放使用者的完整原始問題，不要自行縮短成單一關鍵字，縮短會遺失「怎麼操作/要去哪裡」這類意圖，"
    "導致搜尋不到正確的頁面位置。\n"
    "重要：只要問題屬於這兩類，就必須先呼叫對應工具查詢，不可以在搜尋之前先反問使用者澄清細節；"
    "搜尋完全查不到結果時，才可以請使用者提供更明確的關鍵字。\n"
    "判斷該用哪個工具的關鍵規則：問題裡如果有出現具體的案號數字、姓名或電話號碼，才叫 search_case_records；"
    "只要問題裡沒有提到任何具體案號數字/姓名/電話（即使問題用了「配對」「指派」「請假」這類聽起來像案件操作的字眼），"
    "就一律當作是在問這個功能/頁面怎麼操作，直接呼叫 search_help，絕對不要因為問題裡有這類字眼就反問使用者要查哪個案號。\n"
    "取得工具結果後，請用簡潔的繁體中文口語回答，答案內容必須嚴格根據工具回傳的資料，"
    "不可以用你自己既有的知識編造工具結果裡沒有的資訊。如果答案分散在好幾筆檢索結果裡"
    "（例如一筆說某功能在哪個頁面、另一筆補充操作細節），可以把它們組合拼接成一個完整的回答；"
    "只有當檢索結果整體跟問題完全無關時，才誠實告知使用者查不到相關資訊。\n"
    "判斷是否該拒絕的準則：使用者用「怎麼」「如何」「要怎樣」「要去哪裡」「在哪裡」等疑問語氣詢問某個功能、流程或位置"
    "（例如「休假要怎麼安排」「訂單狀態怎麼看」「月嫂配對要去哪裡操作」），這是在問操作方式或頁面位置，屬於你能回答的範圍，"
    "必須呼叫 search_help，不可以拒絕。只有當使用者直接要求你「幫我改」「把...改成...」"
    "「新增」「刪除」某一筆具體資料時，才需要拒絕並請使用者切換到「✏️ 修改表單」模式，"
    "不要嘗試呼叫任何工具、也不要假裝已經處理。"
)


def _mcp_http_client_factory():
    import httpx2

    internal_key = os.getenv("INTERNAL_API_KEY", "").strip()
    headers = {"X-Internal-API-Key": internal_key} if internal_key else {}
    return httpx2.AsyncClient(headers=headers)


def _call_ollama_chat(messages: list[dict], tools: list[dict]) -> dict:
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_QA_AGENT_MODEL,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0},
            # keep_alive 拉長到 30 分鐘：Ollama 預設閒置 5 分鐘就卸載模型，7b 冷啟動
            # 重新載入要 20~40 秒以上，容易讓使用者以為功能壞掉、或拖到逾時。
            "keep_alive": "30m",
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("message", {})


def _extract_nav_candidates(result_payload: dict) -> list[tuple[str, str | None]]:
    """從 search_help 回傳的 snippets 裡找出所有 navigation_map 附帶的 (url, tab) 候選
    （structured metadata，不是從描述文字裡用正則表達式硬抓）。一次查詢常常會同時撈到
    好幾筆 navigation_map 片段（例如問「服務人員資料要去哪裡看」時，「行事曆導覽」片段
    因為刻意寫了排除語意說明、內含「服務人員基本資料」字樣，語意分數反而可能比真正該去的
    「資料庫瀏覽導覽」還高），這裡先把全部候選收集起來，實際要用哪一個由
    _pick_nav_target() 比對最終回答文字內容決定，不能只憑檢索片段的排序猜。"""
    candidates = []
    for snippet in result_payload.get("snippets", []) or []:
        url = snippet.get("url")
        if url and url in VALID_PAGE_PATHS:
            candidates.append((url, snippet.get("tab")))
    return candidates


# 每個合法頁面/分頁一個獨有的識別字串，用來判斷最終回答文字裡實際提到的是哪一頁——
# 這是比對「回答文字裡客觀上有沒有出現這個頁面的專屬名稱」，跟 _fix_links 驗證網址
# 是否存在同一性質（查證客觀事實），不是在猜測模型的判斷意圖。有 tab 的條目（較具體）
# 排在同一個 url 的通用條目之前，比對時才會優先判定成更精確的深連結。
_NAV_TARGET_KEYWORDS = [
    ("/orders", "accounts_payable", "應付帳款查詢/輸出"),
    ("/orders", None, "訂單與帳務管理系統"),
    ("/calendar", None, "服務人員行事曆與休假安排"),
    ("/finance_alerts", None, "異常警示中心"),
    ("/form_management", None, "表單與履歷問卷管理"),
    ("/data_browser", None, "資料庫原始資料瀏覽"),
    ("/line_management", None, "LINE 管理中心"),
]


# 「行事曆導覽」這筆 navigation_map 內容（build_help_index.py::NAVIGATION_MAP）本身就寫了
# 排除語意（「這裡是排班/請假用的月曆畫面，不是查看服務人員基本資料...的地方，服務人員基本
# 資料要去「🔍 資料庫原始資料瀏覽」查」），目的是幫模型在使用者問錯頁面時能正確引導過去。
# 副作用是：只要「行事曆導覽」片段被撈進候選、且真正該去的是資料庫瀏覽，模型的回答文字常常
# 會同時複誦兩邊的頁面全名（自己的 + 它排除、引導過去的那個），單純比對「文字裡有沒有出現
# 全名」沒辦法分辨模型實際推薦的是哪一個。這不是要猜模型的意圖，是我們自己撰寫、完全掌握的
# navigation_map 內容裡已經寫死的排除關係，用結構化方式直接標記：只要這兩個候選同時出現，
# 一律讓「行事曆導覽」讓位給它自己文字裡指向的那個真正目的地。
_DEFER_TO = {"/calendar": "/data_browser"}


def _pick_nav_target(
    final_message: str, candidates: list[tuple[str, str | None]]
) -> tuple[str | None, str | None]:
    """從整段對話裡所有 search_help 撈到過的候選 (url, tab) 中，挑出跟最終回答文字內容
    對得上的那一個。找不到任何候選跟文字對得上時（例如答案完全沒複誦頁面名稱），才退回
    「第一個候選」當備援，維持舊行為。"""
    if not candidates:
        return None, None
    candidate_set = set(candidates)
    candidate_urls = {url for url, _ in candidate_set}
    for url, tab, keyword in _NAV_TARGET_KEYWORDS:
        if (url, tab) not in candidate_set or keyword not in final_message:
            continue
        defer_url = _DEFER_TO.get(url)
        if defer_url and defer_url in candidate_urls:
            for c_url, c_tab in candidates:
                if c_url == defer_url:
                    return c_url, c_tab
        return url, tab
    return candidates[0]


def _to_full_url(path: str, tab: str | None = None) -> str:
    """把 /orders 這種相對路徑組成可點擊的完整網址，選填帶上 tab 深連結參數。

    刻意不是 http://localhost:8501/orders（Streamlit 原生偵測到的路由）：這個 App 用
    st.sidebar.radio + session_state 的自訂機制切換頁面（ui/nav_helper.py），頁面檔案
    本身刻意不含頂層 show() 呼叫，直接連到原生路由會看到空白頁。改用
    http://localhost:8501/?page=orders，由 ui/app.py::_apply_page_query_param 讀取
    這個網址參數、對應到側邊欄頁面標題後再切換，才會真的顯示內容。

    tab 則是給像「訂單與帳務管理系統」這種頁面內還有多個 st.tabs 分頁的情境用：
    Streamlit 的 st.tabs 沒辦法用程式切換到指定分頁，單純導到頁面還是會停在第一個
    分頁，見 ui/pages/02_orders.py::_render_order_page_shell 裡消費 ?tab= 的邏輯。"""
    slug = path.lstrip("/")
    url = f"{UI_BASE_URL}/?page={slug}"
    if tab:
        url += f"&tab={tab}"
    return url


def _fix_links(message: str, correct_url: str | None, correct_tab: str | None = None) -> str:
    """這個函式只處理「網址對不對／要不要能點／是不是完整網址」這種客觀格式問題，
    不涉及猜測使用者意圖，跟判斷「該不該呼叫哪個工具」是不同性質，所以保留
    （不算是用規則取代模型的判斷）。

    7b 模型偶爾會不理會 navigation_map 提供的正確網址，改從其他片段裡的英文文字
    自己拼出看起來像網址但實際不存在的連結（例如從「(Clients, Orders & Matching)」
    生出「/Clients,Orders&Matching」）。這裡不依賴模型自律，改用程式碼驗證：
    找出訊息裡所有 Markdown 連結，網址（去掉 UI_BASE_URL 前綴後）不在已知合法頁面清單裡的話，
    就用這次對話中 search_help 實際查到的正確網址取代；如果沒查到任何正確網址，
    就把這個連結拿掉（只留文字），避免使用者點到死連結。合法的連結一律組成完整
    http://... 網址，不只給 /orders 這種相對路徑。

    另外，模型有時候會把正確網址直接寫成「網址是 /orders」這種純文字、忘記包成
    Markdown 連結格式，使用者就點不了。如果查到正確網址、但整段回答裡完全沒有
    任何合法連結，就在結尾補上一個可點擊的完整網址連結。"""

    def normalize(url: str) -> str | None:
        """回傳去掉 UI_BASE_URL 前綴後的相對路徑，如果本來就不合法就回傳 None。"""
        candidate = url[len(UI_BASE_URL):] if url.startswith(UI_BASE_URL) else url
        return candidate if candidate in VALID_PAGE_PATHS else None

    def replace(m: re.Match) -> str:
        text, url = m.group(1), m.group(2)
        rel_path = normalize(url)
        if rel_path:
            # 模型自己寫的連結剛好就是這次檢索到的正確頁面時，才順便補上分頁深連結；
            # 其他合法頁面連結不隨便亂加 tab，避免把深連結套到不相關的頁面上。
            tab = correct_tab if correct_url and rel_path == correct_url else None
            return f"[{text}]({_to_full_url(rel_path, tab)})"
        if correct_url:
            return f"[{text}]({_to_full_url(correct_url, correct_tab)})"
        return text

    fixed = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace, message)

    # 只有在整段回答完全沒有任何合法連結時才補一個；如果模型已經自己選對、放了某個
    # 合法連結（不見得是 correct_url，因為同一次檢索可能同時撈到好幾個合法頁面），
    # 就不要再畫蛇添足補第二個進去，之前發生過同時出現兩個連結、其中一個答非所問的情況。
    # 用前綴比對（不含 &tab= 這段）判斷，避免深連結網址（多了 &tab=xxx）被誤判成
    # 「沒有合法連結」而重複補了第二個。
    has_valid_link = any(f"]({_to_full_url(path)}" in fixed for path in VALID_PAGE_PATHS)
    if correct_url and not has_valid_link:
        fixed = f"{fixed}\n\n👉 [前往頁面]({_to_full_url(correct_url, correct_tab)})"

    return fixed


def _extract_tool_result_json(tool_result) -> dict[str, Any]:
    for block in getattr(tool_result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"status": "error", "message": text}
    return {"status": "error", "message": "工具沒有回傳任何內容。"}


# 只帶最近幾輪對話歷史，不是全部：這台機器生成本來就慢，歷史無限累積會讓每次呼叫
# 都要重新處理更長的 context，越聊越慢；只留最近幾輪也足夠讓模型理解「剛剛在問什麼」。
MAX_HISTORY_TURNS = 3


def _history_to_messages(history: list[tuple[str, str]] | None) -> list[dict]:
    """把 ui/app.py session_state 裡的 [(role, content), ...] 對話紀錄轉成 Ollama 訊息格式，
    只取最近 MAX_HISTORY_TURNS 輪（1 輪 = 1 則使用者訊息 + 1 則助理回覆）。"""
    if not history:
        return []
    trimmed = history[-(MAX_HISTORY_TURNS * 2):]
    return [{"role": role, "content": content} for role, content in trimmed]


async def _run_qa_agent_async(user_text: str, history: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    async with streamable_http_client(MCP_ENDPOINT_URL, http_client=_mcp_http_client_factory()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            qa_tools = [t for t in tools_result.tools if t.name in QA_TOOL_NAMES]
            known_tool_names = {t.name for t in qa_tools}
            ollama_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema,
                    },
                }
                for t in qa_tools
            ]

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *_history_to_messages(history),
                {"role": "user", "content": user_text},
            ]

            nav_candidates: list[tuple[str, str | None]] = []

            for _ in range(MAX_TOOL_ITERATIONS):
                message = _call_ollama_chat(messages, ollama_tools)
                native_calls = message.get("tool_calls") or []

                if native_calls:
                    call = native_calls[0]["function"]
                    tool_name, tool_args = call["name"], call["arguments"]
                else:
                    parsed = _extract_tool_call(message.get("content", ""))
                    if parsed is None:
                        content = message.get("content", "").strip()
                        correct_url, correct_tab = _pick_nav_target(content, nav_candidates)
                        final_message = _fix_links(content, correct_url, correct_tab)
                        return {"status": "answered", "message": final_message}
                    tool_name, tool_args = parsed["name"], parsed.get("arguments") or {}

                if tool_name not in known_tool_names:
                    return {
                        "status": "error",
                        "message": f"AI 嘗試呼叫不在問答範圍內的工具「{tool_name}」，已拒絕執行。",
                    }

                tool_result = await session.call_tool(tool_name, tool_args)
                result_payload = _extract_tool_result_json(tool_result)
                if tool_name == "search_help":
                    for candidate in _extract_nav_candidates(result_payload):
                        if candidate not in nav_candidates:
                            nav_candidates.append(candidate)

                messages.append({
                    "role": "assistant",
                    "content": json.dumps({"name": tool_name, "arguments": tool_args}, ensure_ascii=False),
                })
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result_payload, ensure_ascii=False),
                    "name": tool_name,
                })

            return {"status": "error", "message": "已達最大工具呼叫次數仍未得出結論，請簡化你的問題再試一次。"}


def run_qa_agent(user_text: str, history: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """同步入口：供 Streamlit 頁面呼叫。history 是這次提問*之前*的對話紀錄
    [(role, content), ...]（role 為 "user"/"assistant"），讓模型能理解「剛剛在問什麼」，
    不會把使用者對前一個問題的追問/補充當成全新、無上下文的問題來反問。
    回傳其中一種：
    - {"status": "answered", "message": "..."}
    - {"status": "error", "message": "..."}
    """
    return run_with_retry(
        _run_qa_agent_async, user_text, history=history, error_prefix="執行問答助理時發生錯誤"
    )

"""
================================================================================
檔案名稱: services/mcp_form_tools.py
功能說明: MCP Server，將表單欄位查詢/修改建議封裝為可供地端 LLM Agent 呼叫的工具。
         所有工具皆為唯讀/非寫入操作；實際資料庫寫入僅能透過既有的
         PATCH /api/v1/admin/data-browser/{table}/{row_id} 端點、
         由使用者在網頁介面上明確按下確認後觸發，此檔案不直接寫入資料庫。
================================================================================
"""
import hmac
import os
from typing import Literal

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from services import data_browser_admin_schema_service as admin_schema_service
from services import db_service

mcp = MCPServer("LobarUnionFormTools")

# 問答功能（search_help）用的 chromadb collection 名稱。
# 刻意跟 line/worker.py 既有的 "union_faq" collection 分開，避免撞名/混資料。
HELP_INDEX_COLLECTION = "web_admin_help_index"
CHROMA_PERSIST_PATH = "./db/chroma_data"

# 這次「簡易表單修改」功能只開放這三張與案件/人員基本資料相關的表，
# 不比照 admin_schema_service.ALLOWED_TABLES 全開放（那還包含財務、稽核等表）。
FormTable = Literal["clients", "staff", "orders"]


class InternalApiKeyMiddleware:
    """比照 api/dependencies/admin_auth.py::require_internal_service 的驗證方式，
    保護此 MCP 掛載點（find_row 會回傳客戶 PII，不可未經驗證即可存取；
    這條路徑是掛在同一個 FastAPI app 上，經 ngrok 對外時同樣要擋）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        expected = os.getenv("INTERNAL_API_KEY", "").strip()
        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"x-internal-api-key", b"").decode("utf-8", errors="ignore")

        if not expected:
            response = JSONResponse({"detail": "INTERNAL_API_KEY 尚未設定"}, status_code=503)
            await response(scope, receive, send)
            return
        if not provided or not hmac.compare_digest(provided, expected):
            response = JSONResponse({"detail": "內部服務金鑰錯誤"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def build_protected_asgi_app() -> Starlette:
    """回傳套上內部服務金鑰驗證的 MCP Streamable HTTP ASGI app，供 api/main.py 掛載。"""
    inner_app = mcp.streamable_http_app()
    inner_app.add_middleware(InternalApiKeyMiddleware)
    return inner_app


@mcp.tool()
def get_editable_schema(table: FormTable) -> dict:
    """
    取得指定資料表的可編輯欄位白名單、下拉選單選項與主鍵欄位名稱。
    唯讀查詢，不會修改任何資料。呼叫 propose_field_update 前應先確認 field_name
    是否存在於回傳的 editable_columns 清單中。
    """
    try:
        schema = admin_schema_service.get_data_browser_table_schema(table)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    return {
        "status": "ok",
        "table": table,
        "primary_key": schema["primary_key"],
        "editable_columns": schema["editable_columns"],
        "valid_options": schema["valid_options"],
        "read_only": schema["read_only"],
    }


def _locate_row(schema: dict, row_id: str) -> tuple[dict | None, str | None]:
    """依技術主鍵（pk_col）尋找資料列；找不到時，若資料表有 case_no 欄位
    （clients 的真實主鍵其實是 id，使用者口語講的「案號」是 case_no），
    再嘗試以 case_no 比對。回傳 (matched_row, 該列真正的技術主鍵值)。"""
    pk_col = schema["primary_key"]
    for row in schema["rows"]:
        if str(row.get(pk_col)) == str(row_id):
            return row, str(row.get(pk_col))

    if "case_no" in (schema.get("columns") or []) and pk_col != "case_no":
        for row in schema["rows"]:
            if str(row.get("case_no")) == str(row_id):
                return row, str(row.get(pk_col))

    return None, None


@mcp.tool()
def find_row(table: FormTable, row_id: str) -> dict:
    """
    依主鍵值或案號（case_no）查詢單筆資料列目前的欄位內容。
    唯讀查詢，不會修改任何資料。
    """
    try:
        schema = admin_schema_service.get_data_browser_table_schema(table)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    matched_row, resolved_row_id = _locate_row(schema, row_id)
    if matched_row is None:
        return {"status": "error", "message": f"在資料表 {table} 中找不到主鍵值或案號為 {row_id} 的資料列。"}

    return {"status": "ok", "table": table, "row_id": resolved_row_id, "row": matched_row}


@mcp.tool()
def propose_field_update(table: FormTable, row_id: str, field_name: str, new_value: str) -> dict:
    """
    針對指定資料表的單一資料列、單一欄位提出修改建議。

    重要：這個工具只會驗證欄位是否可編輯、資料列是否存在，並回傳「待確認」的異動內容，
    絕對不會寫入資料庫；實際寫入必須由使用者在網頁介面上看到新舊值對照後，
    明確按下確認按鈕才會發生。

    一次只能提出一個欄位的修改建議。如果使用者的指令包含多個欄位的修改，
    請不要自行合併處理，應提示使用者一次只講一個欄位，或針對每個欄位分別呼叫本工具。
    """
    try:
        schema = admin_schema_service.get_data_browser_table_schema(table)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    if schema["read_only"]:
        return {"status": "error", "message": f"資料表 {table} 為唯讀保護，不允許修改。"}

    if field_name not in schema["editable_columns"]:
        return {
            "status": "error",
            "message": (
                f"欄位 '{field_name}' 不在資料表 {table} 的可編輯白名單中，"
                f"可編輯欄位為: {schema['editable_columns']}"
            ),
        }

    matched_row, resolved_row_id = _locate_row(schema, row_id)
    if matched_row is None:
        return {
            "status": "error",
            "message": f"在資料表 {table} 中找不到主鍵值或案號為 {row_id} 的資料列，已取消此建議。",
        }

    valid_options = schema["valid_options"].get(field_name)
    if valid_options and str(new_value) not in [str(v) for v in valid_options]:
        return {
            "status": "error",
            "message": f"欄位 '{field_name}' 的值必須是 {valid_options} 其中之一，收到的是 '{new_value}'。",
        }

    return {
        "status": "pending_confirmation",
        "table": table,
        "row_id": resolved_row_id,
        "primary_key": schema["primary_key"],
        "field_name": field_name,
        "old_value": matched_row.get(field_name),
        "new_value": new_value,
    }


@mcp.tool()
def search_case_records(keyword: str) -> dict:
    """
    依案號、姓名或電話關鍵字搜尋案件，回傳最多 5 筆相符案件的摘要
    （案號、姓名、電話、訂單狀態、服務起訖日）。唯讀查詢，不會修改任何資料。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return {"status": "error", "message": "請提供案號、姓名或電話關鍵字。"}

    # 防呆：LLM 有時會把「案號」「姓名是」等描述詞一起塞進關鍵字（例如「案號115000002」），
    # 導致 LIKE 查詢因為多了描述詞而完全比對不到；這裡先剝除常見描述詞與標點，不依賴模型自律。
    for label in ("案號", "案件編號", "案件", "電話號碼", "電話", "姓名", "名字", "是"):
        keyword = keyword.replace(label, "")
    keyword = keyword.strip(" :：、,，")
    if not keyword:
        return {"status": "error", "message": "請提供案號、姓名或電話關鍵字。"}

    conn = db_service.get_connection()
    try:
        with conn.cursor() as cursor:
            like = f"%{keyword}%"
            cursor.execute(
                """
                SELECT c.case_no, c.name, c.phone, o.status, o.actual_start_date, o.actual_end_date
                FROM clients c
                LEFT JOIN orders o ON o.case_no = c.case_no
                WHERE c.case_no LIKE %s OR c.name LIKE %s OR c.phone LIKE %s
                LIMIT 5
                """,
                (like, like, like),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "ok", "matches": [], "message": f"找不到符合「{keyword}」的案件。"}

    matches = [
        {
            "case_no": row["case_no"],
            "name": row["name"],
            "phone": row["phone"],
            "status": row["status"] or "尚未成立訂單",
            "start_date": str(row["actual_start_date"]) if row["actual_start_date"] else None,
            "end_date": str(row["actual_end_date"]) if row["actual_end_date"] else None,
        }
        for row in rows
    ]
    return {"status": "ok", "matches": matches}


def _bm25_search(collection, question: str, top_n: int = 8) -> list[dict]:
    """向量檢索只看語意，遇到精確詞彙（頁面名稱、專有名詞）有時反而找不到，
    因為語意太抽象。這裡用輕量的 BM25（純 Python，無需額外模型/PyTorch）做字面關鍵字比對，
    跟向量檢索並行、結果取聯集，不是取代向量檢索。索引只有 77 筆內容，每次查詢當場
    重建 BM25 索引即可，不需要額外持久化/快取的複雜度。"""
    import jieba
    from rank_bm25 import BM25Okapi

    everything = collection.get()
    documents = everything.get("documents") or []
    metadatas = everything.get("metadatas") or []
    if not documents:
        return []

    tokenized_corpus = [list(jieba.cut(doc)) for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = list(jieba.cut(question))
    scores = bm25.get_scores(tokenized_query)

    ranked = sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)[:top_n]
    return [
        {
            "content": documents[i],
            "source": (metadatas[i] or {}).get("source"),
            "url": (metadatas[i] or {}).get("url"),
            "tab": (metadatas[i] or {}).get("tab"),
            "distance": None,  # BM25 分數跟向量距離不是同一個量尺，不能直接比較/合併排序
        }
        for i in ranked
        if scores[i] > 0
    ]


@mcp.tool()
def search_help(question: str) -> dict:
    """
    針對「這個網站怎麼操作/某個頁面有什麼功能/某功能要去哪裡找」這類問題，從系統實際頁面內容
    建立的索引中搜尋最相關的說明片段。唯讀查詢，不會修改任何資料。
    索引內容來自實際頁面原始碼（docstring/說明文字），比對外文件更貼近目前真正的功能。
    question 參數請直接放使用者的完整原始問題（例如「月嫂配對要去哪裡操作」），
    不要自行縮短成單一關鍵字（例如只放「月嫂配對」），縮短後會遺失「怎麼操作/要去哪裡」
    這類導覽意圖，導致搜尋不到正確的頁面位置與網址資訊。
    """
    question = (question or "").strip()
    if not question:
        return {"status": "error", "message": "請提供想詢問的操作問題。"}

    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)
    try:
        from services.ollama_embedding import OllamaEmbeddingFunction

        collection = client.get_collection(
            HELP_INDEX_COLLECTION, embedding_function=OllamaEmbeddingFunction()
        )
    except Exception:
        return {
            "status": "error",
            "message": "操作說明索引尚未建立，請先執行 scripts/build_help_index.py。",
        }

    # 向量檢索（語意）：只查一次（n_results=8），在 Python 端把 navigation_map 的結果排到
    # 最前面。原本用兩次 collection.query() (分別查一般內容與 navigation_map) 來確保
    # navigation_map 不被擠掉，但兩次 bge-m3 embedding 呼叫加起來將近 7 秒，實測會偶爾超過
    # MCP Streamable HTTP 的請求時限，導致 SSE 串流中斷 (MCPError: SSE stream ended without
    # a response)。改成只呼叫一次 Ollama embedding，排序邏輯留在本機處理。
    results = collection.query(query_texts=[question], n_results=8)
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    vector_snippets = [
        {
            "content": doc,
            "source": (meta or {}).get("source"),
            "url": (meta or {}).get("url"),
            "tab": (meta or {}).get("tab"),
            "distance": dist,
        }
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]

    # 混合檢索：BM25（字面關鍵字）補向量檢索找不到的精確詞彙，兩邊取聯集（依內容去重）。
    bm25_snippets = _bm25_search(collection, question, top_n=8)
    seen_contents = {s["content"] for s in vector_snippets}
    for s in bm25_snippets:
        if s["content"] not in seen_contents:
            vector_snippets.append(s)
            seen_contents.add(s["content"])

    nav_snippets = [s for s in vector_snippets if s["source"] == "navigation_map"][:2]
    general_snippets = [s for s in vector_snippets if s["source"] != "navigation_map"][:4]
    snippets = nav_snippets + general_snippets

    if not snippets:
        return {"status": "ok", "snippets": [], "message": "索引中沒有找到相關的操作說明。"}

    return {"status": "ok", "snippets": snippets}

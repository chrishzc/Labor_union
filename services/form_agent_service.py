"""
================================================================================
檔案名稱: services/form_agent_service.py
功能說明: 地端 LLM（Ollama, qwen2.5-coder:7b）驅動的表單修改助理服務。
         負責把使用者的自然語言指令，透過 MCP Client 呼叫
         services/mcp_form_tools.py 暴露的唯讀工具，組成一筆「待確認」的
         單一欄位修改建議。此服務本身完全不寫入資料庫；實際寫入永遠只能
         由 UI 在使用者明確確認後，呼叫既有的
         PATCH /api/v1/admin/data-browser/{table}/{row_id} 端點觸發。
================================================================================
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_FORM_AGENT_MODEL = os.getenv("OLLAMA_FORM_AGENT_MODEL", "qwen2.5-coder:7b")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
MCP_ENDPOINT_URL = f"{API_BASE_URL}/mcp-tools/mcp"
MAX_TOOL_ITERATIONS = 4

# MCP server 上還掛著 search_case_records/search_help (問答用途)，這裡只暴露表單修改相關的工具，
# 避免無關工具稀釋模型對 propose_field_update 該用哪張表/欄位的判斷（實測發現多餘工具會讓模型選錯表）。
FORM_TOOL_NAMES = {"get_editable_schema", "find_row", "propose_field_update"}

SYSTEM_PROMPT = (
    "你是 Lobar Union 系統的表單修改助理。使用者會用自然語言描述想修改的資料欄位，"
    "你可以使用工具查詢資料表結構與現有資料，並針對「單一欄位」提出修改建議。"
    "如果使用者的指令跟修改表單資料無關，或是要求的操作不在你能使用的工具範圍內"
    "（例如刪除資料），請直接用文字回覆說明你無法處理，不要呼叫任何工具。"
    "如果使用者一次要求修改多個欄位，請只處理其中一個，並在文字回覆中請使用者針對其餘欄位分開再問一次。"
)


def _extract_tool_call(content: str) -> dict[str, Any] | None:
    """Ollama 對 qwen2.5-coder 系列不會把工具呼叫寫進結構化 tool_calls，
    一律落在 content 裡的裸文字，需要自行解析。"""
    text = (content or "").strip()
    text = re.sub(r"^```json\s*|```$", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"</?tool_call>", "", text).strip()

    for candidate in (text, re.sub(r'("name"\s*:\s*)([A-Za-z_][A-Za-z0-9_]*)', r'\1"\2"', text)):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
            return obj
    return None


def _call_ollama_chat(messages: list[dict], tools: list[dict]) -> dict:
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_FORM_AGENT_MODEL,
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


def _mcp_http_client_factory():
    import httpx2

    internal_key = os.getenv("INTERNAL_API_KEY", "").strip()
    headers = {"X-Internal-API-Key": internal_key} if internal_key else {}
    return httpx2.AsyncClient(headers=headers)


async def _run_form_agent_async(user_text: str) -> dict[str, Any]:
    async with streamable_http_client(MCP_ENDPOINT_URL, http_client=_mcp_http_client_factory()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            form_tools = [t for t in tools_result.tools if t.name in FORM_TOOL_NAMES]
            known_tool_names = {t.name for t in form_tools}
            ollama_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema,
                    },
                }
                for t in form_tools
            ]

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ]

            for _ in range(MAX_TOOL_ITERATIONS):
                message = _call_ollama_chat(messages, ollama_tools)
                native_calls = message.get("tool_calls") or []

                if native_calls:
                    call = native_calls[0]["function"]
                    tool_name, tool_args = call["name"], call["arguments"]
                else:
                    parsed = _extract_tool_call(message.get("content", ""))
                    if parsed is None:
                        return {"status": "no_action", "message": message.get("content", "").strip()}
                    tool_name, tool_args = parsed["name"], parsed.get("arguments") or {}

                if tool_name not in known_tool_names:
                    return {
                        "status": "error",
                        "message": f"AI 嘗試呼叫不存在的工具「{tool_name}」，已拒絕執行。",
                    }

                tool_result = await session.call_tool(tool_name, tool_args)
                result_payload = _extract_tool_result_json(tool_result)

                if tool_name == "propose_field_update":
                    return result_payload

                # get_editable_schema / find_row 屬於資訊蒐集步驟，把結果餵回模型繼續下一步
                messages.append({"role": "assistant", "content": json.dumps({"name": tool_name, "arguments": tool_args}, ensure_ascii=False)})
                messages.append({"role": "tool", "content": json.dumps(result_payload, ensure_ascii=False), "name": tool_name})

            return {"status": "error", "message": "已達最大工具呼叫次數仍未得出結論，請簡化你的指令再試一次。"}


def _extract_tool_result_json(tool_result) -> dict[str, Any]:
    for block in getattr(tool_result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"status": "error", "message": text}
    return {"status": "error", "message": "工具沒有回傳任何內容。"}


def run_with_retry(async_fn, *args, error_prefix: str, attempts: int = 2, **kwargs) -> dict[str, Any]:
    """MCP Streamable HTTP session 偶爾會因為連線/session 生命週期的競速情況丟出
    TaskGroup 例外（實測常見於 FastAPI --reload 剛好在請求進行中重啟的瞬間）；
    這類錯誤重試一次幾乎都會成功，不應該直接把技術性錯誤訊息丟給使用者看。"""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return asyncio.run(async_fn(*args, **kwargs))
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(1)
    return {"status": "error", "message": f"{error_prefix}: {last_error}"}


def run_form_agent(user_text: str) -> dict[str, Any]:
    """同步入口：供 Streamlit 頁面呼叫。回傳其中一種：
    - {"status": "pending_confirmation", "table", "row_id", "primary_key", "field_name", "old_value", "new_value"}
    - {"status": "error", "message"}
    - {"status": "no_action", "message"}
    """
    return run_with_retry(_run_form_agent_async, user_text, error_prefix="執行 AI 助理時發生錯誤")

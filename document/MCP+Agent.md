# Lobar Union 系統打包 MCP 與地端行政小助理建設規畫書

本文件規劃如何將 Lobar Union 的後端 API 與服務打包為 **Model Context Protocol (MCP)** 伺服器，並利用**地端大型語言模型 (Local LLM)** 建設一個能夠理解使用者自然語言語意、熟知業務邏輯，並能自動操作系統的「簡易行政小助理」。

---

## 1. 專案目標與應用場景

在月子照顧（月嫂）的行政流程中，行政人員需要頻繁地在訂單管理、月嫂媒合、Line 訊息推送以及最複雜的**出勤排假與結束日順延精算**之間進行切換。

透過建置 **MCP 伺服器** 與 **地端 AI 行政助理**，可以實現以下場景：
- **自然語言排假精算**：「*月嫂阿美在 10/5 ~ 10/7 要請假 3 天，幫我重新計算訂單 #102 的結束日期並儲存排班。*」
- **自動化媒合與推播**：「*幫我推薦適合訂單 #105 的月嫂，並把粗篩資訊發送給她們。*」
- **一鍵查詢與合約準備**：「*幫我查一下客戶王小美的訂單狀況，並預覽她的合約資訊。*」

在地端運行開源 LLM（如 Qwen2.5-Coder、Llama 3.1），除了**完全免費**外，更能**確保客戶隱私與訂單資料不會外流至公有雲端模型**。

---

## 2. MCP 伺服器架構設計 (MCP Server)

我們將使用 Anthropic 官方的 `mcp` Python SDK，基於 `FastMCP` 快速將 Lobar Union 的服務層或 API 封裝為 MCP Tools。

### 2.1 技術選型
- **開發套件**：`mcp[cli]` (Python SDK)
- **通訊協定**：預設採用 `stdio`（標準輸入輸出，適合 IDE 與本地 Agent 直接調用）；可選用 `SSE` (Server-Sent Events) 作為 HTTP 跨進程呼叫。
- **整合方式**：直接調用 `services/db_service.py` 的 API 或是呼叫本地運行的 FastAPI 端點。

### 2.2 MCP Tools 封裝清單 (Tools Mapping)

MCP 伺服器將暴露以下 Tools 給 LLM：

| 工具名稱 (`tool_name`) | 對應 API / 服務層功能 | 參數說明 | 描述 / 業務規則 |
| :--- | :--- | :--- | :--- |
| `get_orders` | `GET /api/v1/orders` | `status` (Optional) | 取得所有訂單的基本狀態與列表 |
| `get_order_details` | `GET /api/v1/orders/{order_id}` | `order_id` (Required) | 取得單筆訂單之 36 欄位詳細試算資訊 |
| `calculate_schedule` | `POST /api/v1/orders/calculate-schedule` | `order_id`, `custom_leaves`, `holidays_off` | **出勤天數精算**：傳入請假日期與國定假日放假名單，回傳順延後之 `actual_end_date` 與每日排班狀態 |
| `save_schedule` | `POST /api/v1/schedule/save` | `order_id`, `schedule_data` | 將精算後的排班紀錄與順延完工日寫入資料庫 |
| `recommend_staff` | `GET /api/v1/matches/recommend-staff` | `order_id` | 根據訂單需求，依檔期與地區推薦合適月嫂 |
| `send_match_notification` | `POST /api/v1/matches/{match_id}/send-info-{step}` | `match_id`, `step` (1: 粗篩, 2: 精篩, 3: 履歷) | 透過 Line 推播媒合資訊或履歷給月嫂或客戶 |
| `assign_staff` | `POST /api/v1/orders/{order_id}/assign-staff` | `order_id`, `staff_id` | 正式定案指派月嫂，鎖定檔期並建立訂單 |
| `manage_holidays` | `GET/POST/DELETE /api/v1/holidays` | `action` (list/add/delete), `holiday_date` | 管理系統內的國定假日名單 |

---

## 3. 地端行政小助理 Agent 設計

小助理作為 Local Agent Client，藉由 `Ollama` 驅動地端 LLM，並使用 MCP SDK 連接上述 MCP 伺服器，解析使用者的自然語言並進行多步驟工具調用。

### 3.1 LLM 引擎與模型選型
- **模型推理引擎**：**Ollama**（本地一鍵部署，支援 Tool Calling 功能）。
- **推薦模型**：`qwen2.5-coder:7b-instruct` 或 `llama3.1:8b`。
  - *註：Qwen 2.5 Coder 在 7B 等級中具有極強的 Function-calling 與邏輯推理能力，極適合本專案。*

### 3.2 核心業務 Prompt (System Instructions)
為確保 Agent 嚴格遵守系統的「業務公理」與操作流程，System Prompt 設計如下：

```markdown
# 角色
你是 Lobar Union 系統的 AI 行政小助理。你負責協助行政人員處理訂單、安排月嫂檔期、精算請假順延，以及發送 Line 媒合推播。

# 核心業務知識與操作規範
1. 兩階段選單與操作隔離：
   - 洽談中案件（無 actual_start_date）：只能進行「訂單匹配 (recommend_staff)」，在月曆上僅能做預排與 7 天備用期展示，嚴禁執行出勤天數精算。
   - 確定開始日案件（有 actual_start_date）：才可啟動「出勤天數精算 (calculate_schedule)」，進行工作日與請假休假管理。
2. 綠底休假與結束日動態順延公理：
   - 只要有任何請假/休假（不論是自訂請假 custom_leaves 或是選擇放假的國定假日 holidays_off，在月曆上皆以綠底標示），每增加 1 天，服務結束日期 actual_end_date 必須向後順延 1 天，以確保實際工作天數足額。
   - 請假調整後，必須呼叫 `calculate_schedule` 試算，再呼叫 `save_schedule` 進行持久化。
3. 國定假日單日獨立決策：
   - 當使用者提到國定假日（如端午連假、中秋節）時，應向行政確認各別日期是否放假。放假者計入 holidays_off 並順延結束日；不放假者為正常工作日。
4. 媒合推播流程順序：
   - 行政操作順序必須為：推薦人員 -> 發送訂單資訊-1 -> 收到意願後發送資訊-2 -> 傳送履歷給客戶 -> 客戶同意後定案指派 (assign_staff)。請引導行政人員按步驟操作。
5. 數值安全公理：
   - 所有費用、天數計算均為整數，無小數點。
```

---

## 4. 極簡實作方案 (Ponytail 模式 - 最精簡代碼)

遵循 **Ponytail 模式**，我們不引入複雜的 LangChain 框架，而是使用 Python 官方的 `mcp` SDK 與 `ollama` 原生 Python 套件，用最少代碼實現 MCP 伺服器與 Agent。

### 4.1 MCP 伺服器端 (`scripts/mcp_server.py`)

```python
# -*- coding: utf-8 -*-
"""
Lobar Union MCP Server
- 基於 FastMCP 提供地端 LLM 呼叫系統 API 的能力
"""
import sys
from mcp.server.fastmcp import FastMCP
import requests

# 初始化 FastMCP
mcp = FastMCP("LobarUnionAdmin")
API_BASE_URL = "http://localhost:8000/api/v1"

@mcp.tool()
def get_order_details(order_id: int) -> str:
    """取得單筆訂單的詳細 36 欄位資訊與當前結束日。"""
    try:
        response = requests.get(f"{API_BASE_URL}/orders/{order_id}")
        return str(response.json())
    except Exception as e:
        return f"無法取得訂單資訊: {str(e)}"

@mcp.tool()
def calculate_and_save_schedule(order_id: int, custom_leaves: list, holidays_off: list) -> str:
    """
    計算並儲存出勤排假。
    custom_leaves: 請假日期列表 (例如 ['2026-10-01'])
    holidays_off: 放假的國定假日日期列表
    每次休假均會將結束日 (actual_end_date) 順延 1 天。
    """
    try:
        # 1. 呼叫精算 API
        calc_payload = {"custom_leaves": custom_leaves, "holidays_off": holidays_off}
        calc_res = requests.post(f"{API_BASE_URL}/orders/{order_id}/calculate-schedule", json=calc_payload)
        if calc_res.status_code != 200:
            return f"試算失敗: {calc_res.text}"
        
        schedule_data = calc_res.json()
        
        # 2. 儲存排班結果
        save_res = requests.post(f"{API_BASE_URL}/schedule/save", json={
            "order_id": order_id,
            "actual_end_date": schedule_data.get("actual_end_date"),
            "schedule_days": schedule_data.get("days")
        })
        if save_res.status_code != 200:
            return f"儲存排班失敗: {save_res.text}"
            
        return f"成功！新完工日順延至: {schedule_data.get('actual_end_date')}，排假已存入系統。"
    except Exception as e:
        return f"執行過程中發生錯誤: {str(e)}"

@mcp.tool()
def recommend_and_match_staff(order_id: int) -> str:
    """根據訂單推薦合適的服務人員（月嫂）。"""
    try:
        response = requests.get(f"{API_BASE_URL}/matches/recommend-staff?order_id={order_id}")
        return str(response.json())
    except Exception as e:
        return f"推薦失敗: {str(e)}"

if __name__ == "__main__":
    # 以 stdio 模式運行 MCP 伺服器
    mcp.run(transport="stdio")
```

### 4.2 Agent 用戶端 (`services/agent_service.py`)

使用 `ollama` SDK 自動解析使用者的自然語言，並根據 MCP 提供的 Tools 進行 Tool Calling。

```python
# -*- coding: utf-8 -*-
"""
Lobar Union Agent Service
- 串接本地 Ollama 與 MCP Server，執行語意操作
"""
import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import json

# 配置 MCP 伺服器參數
server_params = StdioServerParameters(
    command="python",
    args=["scripts/mcp_server.py"]
)

async def run_admin_agent(user_prompt: str):
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. 初始化並列出 MCP Tools
            await session.initialize()
            mcp_tools = await session.list_tools()
            
            # 將 MCP tools 轉換為 Ollama 接受的 format
            ollama_tools = []
            for tool in mcp_tools.tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })

            # 2. 呼叫地端 Ollama 模型
            system_prompt = "你是 Lobar Union 系統的 AI 行政助理。請利用工具協助完成使用者的操作。"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = ollama.chat(
                model="qwen2.5-coder:7b",
                messages=messages,
                tools=ollama_tools
            )

            # 3. 處理 Tool Calling 迴圈
            tool_calls = response.get("message", {}).get("tool_calls", [])
            if tool_calls:
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = tool_call.function.arguments
                    
                    # 執行 MCP Tool
                    result = await session.call_tool(func_name, func_args)
                    
                    # 將結果餵回模型以產生最終語意回覆
                    messages.append(response["message"])
                    messages.append({
                        "role": "tool",
                        "content": str(result.content),
                        "name": func_name
                    })
                    
                final_response = ollama.chat(
                    model="qwen2.5-coder:7b",
                    messages=messages
                )
                return final_response["message"]["content"]
            else:
                return response["message"]["content"]

# 簡易測試入口
if __name__ == "__main__":
    prompt = "幫我計算訂單 #102 的月嫂在 10/10 請假一天的排程，並幫我存檔。"
    print(asyncio.run(run_admin_agent(prompt)))
```

---

## 5. Streamlit 介面整合 (AI Assistant Page)

我們將在現有的 Streamlit 介面中新增一個專屬頁面：`ui/pages/06_ai_assistant.py`。
此頁面將提供一個極具現代感的 Chat 介面。

### 5.1 頁面功能設計
1. **對話視窗**：使用 Streamlit `st.chat_message` 與 `st.chat_input` 構建互動式對話。
2. **快速操作卡片**：提供「請假順延試算」、「今日媒合推薦」、「推播 Line 通知」等一鍵填入範本 Prompt 的按鈕。
3. **執行歷程 (Execution Logs) 面板**：在對話旁顯示 Agent 當前呼叫的工具、傳入參數與 API 回傳，讓行政人員清楚知道 AI 做了什麼操作，達到透明、安全防呆。

### 5.2 Streamlit 程式碼結構 (`ui/pages/06_ai_assistant.py`)

```python
import streamlit as st
import asyncio
from services.agent_service import run_admin_agent

st.set_page_config(page_title="AI 行政小助理", layout="wide")
st.title("🤖 Lobar Union AI 行政小助理")
st.caption("用地端 Qwen 模型與 MCP 協定，100% 隱私保護的自然語言系統操作工具。")

# 初始化對話歷史
if "messages" not in st.session_state:
    st.session_state.messages = []

# 繪製歷史對話
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 輸入框
if user_input := st.chat_input("請輸入操作指令... (例如：幫我精算訂單 102，月嫂在 10/22 請假 1 天)"):
    # 顯示使用者訊息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 執行 Agent 邏輯
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        with st.spinner("AI 正在思考與操作系統中..."):
            # 呼叫 Agent 服務
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(run_admin_agent(user_input))
            message_placeholder.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
```

---

## 6. 部署與啟動指南

### 6.1 一鍵啟動腳本整合 (`start.bat`)
修改根目錄的 `start.bat`，在啟動 FastAPI 與 Streamlit 時，確保地端 Ollama 服務有正常啟動。
我們可以在 `start.bat` 中加入 Ollama 檢測邏輯：

```bat
:: 檢查 Ollama 是否運行，若無則啟動
tasklist | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo [INFO] 正在啟動 Ollama 服務...
    start "" "C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama app.exe"
    timeout /t 5
)

:: 確保本地加載了 Qwen2.5-Coder 模型
ollama pull qwen2.5-coder:7b
```

### 6.2 對接外部 IDE 與 Client (如 Claude Desktop)
本專案開發的 MCP Server 同時可被外部支援 MCP 的 Client（如 Claude Desktop 或 Cursor）直接連線，便於開發者調用。
在 `C:\Users\TMP-214\AppData\Roaming\Claude\claude_desktop_config.json` 中加入以下配置：

```json
{
  "mcpServers": {
    "lobar-union-admin": {
      "command": "python",
      "args": [
        "C:/Users/TMP-214/Desktop/project/Lobar_union---solo/scripts/mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "C:/Users/TMP-214/Desktop/project/Lobar_union---solo"
      }
    }
  }
}
```

---

## 7. ADAD 系統地圖註冊 (System Map Registration)

為了符合 **ADAD 規範 (RULE-01/RULE-02)**，在實作上述代碼前，應將新模組登載於 `system_map.yaml`：

```yaml
  MCPServer:
    type: script
    description: Lobar Union 系統專用 MCP 服務，將 API 封裝為 LLM 可調用之 Tools。
    source: '`scripts/mcp_server.py`'
    dependencies: [APILayer]
    state: planned
  
  AIAssistantAgent:
    type: service
    description: 基於 Ollama 與 Qwen2.5-Coder 的地端 AI 行政助理，連接 MCP Server 執行語意操作。
    source: '`services/agent_service.py`'
    dependencies: [MCPServer]
    state: planned

  AIAssistantUI:
    type: ui_page
    description: Streamlit AI 助手對話介面。
    source: '`ui/pages/06_ai_assistant.py`'
    dependencies: [AIAssistantAgent]
    state: planned
```

此設計將完美融合系統的「出勤精算順延」、「兩階段隔離」與「資料庫安全」公理，實現地端高效、高隱私的 AI 自動化運營。

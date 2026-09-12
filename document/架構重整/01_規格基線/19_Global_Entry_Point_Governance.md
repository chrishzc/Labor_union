# Global Entry Point Governance

## 1. Current boundary

管理端唯一 current UI source 是 `ui_react/`。舊 `ui/` Streamlit tree 已於 2026-09-02 依人工裁決從工作樹移除；不得再把 Git 歷史、舊文件、舊測試、rollback metadata 或 generated queue 當成 current entry evidence。

正式管理端入口由兩個直接事實共同成立：

1. `ui_react/src/components/MasterLayout.tsx` 宣告可達 navigation entry；
2. `ui_react/src/App.tsx` 對相同 page identity 有實際 render branch。

只有其中之一存在時視為 registry drift，不得宣稱功能可達。

## 2. Current React entries

下列清單記錄現行 navigation 與 render branch 的共同 identity，不另行定義業務功能或復活已退役入口：

- `order-workbench-v2`
- `scheduling`
- `staff`
- `clients`
- `data-import`
- `reports`
- `line-management`
- `line-ai-events`
- `line-llm-settings`
- `line-liff-studio`
- `line-security`
- `finance`
- `historical-service-accounting`
- `anomalies`
- `account-management`
- `storage-management`

依 `33_案件與月嫂整合名冊正式規格.md` 的名冊裁決，`data-browser` 相容深連結顯示客戶名冊，不再開啟 `DataImportPage` 的六來源分頁。现行 `databrowser` 與 `client-roster` aliases 亦映射至 `clients`，使用同一個 `ClientRegistryPage`；此為頁面解析，不要求網址立即改寫。

`order-tracker`、`orders` 與獨立 `system-status` 已不在上述正式導航及 render branches。系統狀態的既有 snapshot Query 與 shell 指示器仍保留，不因獨立頁面退出而刪除。

## 3. Removed Streamlit surface

下列資產已退役，不得復活為 current dependency：

- `ui/` 與 `.streamlit/`
- Streamlit API clients、pages、components 與 navigation helper
- Streamlit rollback deep links
- `react_admin_entrypoints.json` 與 `react_admin_retirement_requirements.json`
- `entrypoint_review_queue_v1.jsonl` 與只為該 queue 存在的 generator／validator
- Streamlit compatibility Docker image、build、setup 與 publish scripts
- 直接 import 或讀取 `ui/` source 的測試

歷史內容需要追溯時從 Git history 讀取，不回存 current worktree。

## 4. API 與 CLI entry

API endpoint 與 operator CLI 需依 current objective 個別判定：

- current owner 與實際用途；
- public／operator contract；
- replacement 是否存在；
- source removal 後是否仍有 current caller；
- focused regression 或直接 readback。

不得因 UI 已改為 React，自動刪除仍被 React、worker、provider 或操作人員使用的 API／CLI。

Data Browser 依規格 33 保留 `GET /api/v1/admin/data-browser/sources/{source_id}` 的 authenticated、bounded archive Query。舊 `GET /api/v1/admin/data-browser/{table}` raw table metadata 與 generic PATCH／source-correction 不屬此保留範圍；其路由已移除，不提供原始 rows、欄位或舊 editable metadata，也不新增相容 writer。Smoke 工具使用現行 OpenAPI 與明確 fixture，不自動展開原始資料表。

## 5. Standard local runtime

標準本機管理端固定為：

1. FastAPI `127.0.0.1:8000`
2. React/Vite `127.0.0.1:5173/admin/`

`scripts/launchers/start_local_development.bat` 與 `.sh` 不得啟動 Streamlit、檢查 8501，或要求 `ui/app.py`。React 透過 relative `/api` proxy 呼叫同一 FastAPI owner。

`--dry-run` 只檢查 current dependencies；`--smoke-test` 只建立本次擁有的 FastAPI＋React process，執行 GET-only readiness 後清理。

## 6. Verification

管理端 entry 的最低充分驗證是：

- navigation identity 存在；
- render branch 存在；
- page module 可被 TypeScript build／test 載入；
- 直接相關 typed API client 與 focused UI test 通過。

不得再要求 Streamlit rollback、retention window、removal receipt 或舊 queue 一致性來驗證 current React entry。

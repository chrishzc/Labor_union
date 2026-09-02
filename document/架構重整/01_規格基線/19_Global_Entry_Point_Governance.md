# Global Entry Point Governance

## 1. Current boundary

管理端唯一 current UI source 是 `ui_react/`。舊 `ui/` Streamlit tree 已於 2026-09-02 依人工裁決從工作樹移除；不得再把 Git 歷史、舊文件、舊測試、rollback metadata 或 generated queue 當成 current entry evidence。

正式管理端入口由兩個直接事實共同成立：

1. `ui_react/src/components/MasterLayout.tsx` 宣告可達 navigation entry；
2. `ui_react/src/App.tsx` 對相同 page identity 有實際 render branch。

只有其中之一存在時視為 registry drift，不得宣稱功能可達。

## 2. Current React entries

Current navigation identity 包含：

- `order-tracker`
- `orders`
- `scheduling`
- `staff`
- `data-import`
- `reports`
- `line-management`
- `line-ai-events`
- `line-liff-studio`
- `line-security`
- `finance`
- `anomalies`
- `account-management`
- `system-status`

`data-browser` 保留為 React compatibility hash identity，實際 render 同一個 `DataImportPage` 的 data-browser 分頁；不建立第二份 UI owner。

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

本裁決只簡化已退役的 Streamlit surface。API endpoint 與 operator CLI 仍需依 current objective 個別判定：

- current owner 與實際用途；
- public／operator contract；
- replacement 是否存在；
- source removal 後是否仍有 current caller；
- focused regression 或直接 readback。

不得因 UI 已改為 React，自動刪除仍被 React、worker、provider 或操作人員使用的 API／CLI。

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

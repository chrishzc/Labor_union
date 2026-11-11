# Global Entry Point Governance

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global Entry Point / Shell Governance
- 單一負責範圍：管理端 React 正式導航／render 路由、相容 hash alias、已停用 API（410 Gone）邊界、本機標準開發入口與 NAS 維護腳本契約。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)、[案件與月嫂整合名冊正式規格](33_案件與月嫂整合名冊正式規格.md)

## 2. 管理端 React 正式入口

管理端唯一前端為 `ui_react/`。正式入口必須同時存在於以下兩處，僅存其一即視為 registry drift：

1. `ui_react/src/components/MasterLayout.tsx` 宣告可達 navigation entry；
2. `ui_react/src/App.tsx` 對相同 page identity 具備 render branch。

### 2.1 現行導航與頁面清冊

- `order-workbench-v2`
- `scheduling`
- `staff`
- `clients`（`#data-browser`、`#databrowser`、`#client-roster` alias 均解析至此頁，使用 `ClientRegistryPage`）
- `data-import`
- `reports`
- `line-management` — 客服與營運（客服案件、身分與授權、案件群組）
- `line-notifications` — 通知與寄送（通知與發送、寄送與異常）
- `line-interface` — LINE 介面設定（圖文選單、表單、LINE 流程圖）
- `line-ai-events` — AI 客服工作室（常見問答、引導動作、回答測試、回饋分析、模型設定）
- `finance`
- `accounting-parameters`
- `payment-reminder-settings` — 帳務通知排程條件與 10 則帳務 LINE 範本設定
- `database-backup` — 每日備份時間與狀態（owner 為 [NAS Fresh 初始化與維護復原](10A_NAS_Fresh初始化與維護復原規格.md)）
- `account-management`
- `contract-templates`

### 2.2 相容 Deep Link 解析規則

- `#line-llm`／`#line-llm-settings` → `line-ai-events` 模型設定分頁。
- `#line-studio`／`#line-liff-studio` → `line-interface` 表單分頁。
- `#line-management?tab=push_queue|delivery|richmenu|message_flow|liff` → 依責任導向 `line-notifications` 或 `line-interface`。
- `#finance?tab=payment-destination` → 導向 `finance` 每月帳務。
- 已移除側欄入口之未知或 retired hash（包含 `#anomalies`、`#storage-management`、`#file-settings`、`#historical-service-accounting`、`#line-security`、`#order-tracker`、`#orders`、`#system-status`）：沿用 App 未知 hash 預設規則顯示待辦看板，不建立替代獨立頁面。
- `system-status` 雖無獨立頁面，仍保留右上角 shell 狀態指示器與 `GET /api/v1/system/status/performance-snapshot` 唯讀 Query。

## 3. API 與 CLI 入口治理與已停用契約

### 3.1 入口保留判斷基準

API endpoint 與 operator CLI 不得僅因前端無 static caller 即刪除，必須逐一確認 current owner、public／operator contract、replacement、實際 callers 與 focused readback。

### 3.2 已停用／移除之端點與替代邊界

- **銀行無案件人工新增**：`POST /api/v1/finance-import/statements/manual` 經認證後固定回 typed 410；案件手動補登改用案件抽屜正式補登入口。既有備查紀錄另保留 `GET /api/v1/finance-import/statements/manual/export` 唯讀下載。
- **政府補助舊逐案入口**：改用 `/api/v1/government-subsidy/periods` 月／季／年整期核銷；原 claim planning／submission／approval、逐案 receipt、offset 與 advance settlement POST 端點回 410，durable worker 拒絕建立舊命令；歷史 Query 與原交易沖正保留。
- **舊帳戶維護端點**：`/api/v1/client-finance/payment-destination`（GET、`/preview`、`/apply`）已自路由與 OpenAPI 移除。
- **月嫂履歷暫存下載**：`GET /api/v1/matching-confirmation-files/{token}` 回 typed 410 Gone；履歷改由業務線下傳送，LINE 排班確認卡片不嵌入下載連結。
- **Data Browser 原始資料表端點**：僅依名冊契約保留 `GET /api/v1/admin/data-browser/sources/{source_id}` 之 authenticated bounded archive Query；移除 `GET /api/v1/admin/data-browser/{table}` raw table metadata 與 generic PATCH／source-correction 路由。
- **非市民歷史補登**：移除表單與 `POST /api/v1/admin/registration-applications/manual-non-citizen/check`，手動建案只接受後端正式配號的新案。既有案件及虛擬帳號對照保留。
- **HCM 修正版工作簿端點**：移除 `/api/v1/case-import/hcm/resubmissions/{preview|apply}` 與頁面入口；保留 `/hcm/reviews`、單筆 Query、逐欄略過、一般 workbook intake 與既有 outbox／證據。
- **管理員通知對象設定**：移除 `line-security` 頁與 mutation；管理員系統狀態顯示於 `line-mobile-admin?target=staff_review` 頂端唯讀卡片，歷史 target 查詢保留。
- **歷史服務天數與檔案／異常頁面**：前端獨立側欄入口移除（歷史服務天數操作內嵌於客戶名冊詳情抽屜），既然後端 Q/P/A、30 天排程清理（`run_automatic_retention_cycle`）與資料保留。

### 3.3 Windows NAS 維護入口

- `initialize_nas_schema.bat`：僅執行備份後的 candidate 安全升級，不委派 fresh／reset（低階 Python／Unix `.sh` 仍保留供 disposable 環境測試）。
- `backup_nas_database.bat` 與 `restore_nas_database.bat`：提供明確備份／還原操作。
- `GET /api/v1/system/database-backup` 與 `PUT /api/v1/system/database-backup/schedule`：限已認證管理員查閱狀態與設定每日備份時間，不提供 reset、SQL 執行、備份下載或網頁復原。

## 4. Standard local runtime

標準本機管理端固定為：

1. FastAPI `127.0.0.1:8000`
2. React/Vite `127.0.0.1:5173/admin/`

`scripts/launchers/start_local_development.bat` 與 `.sh` 僅啟動 FastAPI 與 React/Vite（透過 relative `/api` proxy 連線）。`--dry-run` 僅檢查 current dependencies；`--smoke-test` 僅啟動 owned FastAPI＋React 執行 GET-only readiness 後清理。

## 5. 驗收標準

管理端入口的最低充分驗證為：

- `MasterLayout.tsx` navigation identity 存在；
- `App.tsx` render branch 存在；
- page module 可被 TypeScript build／test 載入；
- 直接相關 typed API client 與 focused UI test 通過；
- 已停用 410／移除路由均回傳預期 typed status 且無寫入副作用。

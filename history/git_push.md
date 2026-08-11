## 📌 更新摘要

本次更新將 merge 分支的 LINE 一般用戶服務入口、月嫂自助查詢、客服管理與新版預設選單介面，依 canonical 新架構完整移植至 wen 分支；同時新增 LINE 身分查詢、對象更正與安全解除功能。所有受保護 LIFF 操作均以 LINE 驗證身分、正式 identity binding 與既有 assignment 權限為邊界，管理端 mutation 透過 typed API、資料庫交易、durable outbox 與 Worker 執行，不讓 Streamlit 或瀏覽器直接承擔業務規則。

本版也修正首次 LINE Login 授權回跳、LIFF additional information context 遺失、過期流程未在開頁時拒絕，以及未填表客戶完成登記後未續行身分綁定等問題；並同步更新 Rich Menu 圖面、預設按鈕、管理中心名稱、正式規格、release migration 與協作規範。

## 🆕 新增功能與檔案

- **LINE 客服與服務說明**
  - 新增 canonical Customer Service Domain、typed contracts、application service 與 MySQL repository，保存客服需求、狀態、版本、actor、冪等資訊及事件軌跡。
  - 新增「服務說明」Webhook handler，提供服務流程、收費與補助、進度查詢、修改資料、聯絡工會及其他問題等入口，並維持 identity、group、service help、knowledge fallback 的固定分派順序。
  - 新增 Customer Service 管理 API、typed schemas、bounded UI API client 與 LINE 管理中心「客服入口」，支援摘要、列表、明細、狀態／內部備註更新及可靠 LINE 回覆。

- **月嫂 LIFF 自助服務**
  - 新增 verified staff self-service API，以及月嫂訂單查詢與月班表 LIFF 頁面。
  - 操作者身分由已驗證 LINE identity 對應正式 staff subject；查詢範圍固定限制在本人有效 assignment，姓名與案件編號只能縮小結果，不能擴大授權。
  - 班表只讀取 Scheduling-owned projection，不在 LINE 子系統另建排班 writer。

- **LINE 身分管理與解除**
  - 新增身分綁定列表、篩選、明細、同 subject type 對象更正、解除預覽／套用、重試與人工完成等 typed commands、queries、API 與 bounded UI client。
  - LINE 管理中心新增「身分管理」頁面，依 read／manage／override capability 控制查詢、更正、解除與人工處理權限。
  - 解除採 Rich Menu-first durable saga：先將 binding 轉為 `revocation_pending` 並建立 outbox；Worker 成功套用 canonical 一般用戶選單後，才清除 `clients`、`staff` 或 `admin_users` 的 LINE owner projection，最後完成 `revoked`。
  - 解除過程保留 binding root、provider menu、attempt、error、actor、reason、idempotency key、correlation ID 與時間紀錄，不刪除個人及工會歷史資料。

- **Schema 與 release artifacts**
  - 新增 `166_customer_service_runtime.sql` 與 Stage 11 descriptor／release manifest。
  - 新增 `167_line_identity_management.sql` 與 Stage 12 descriptor／release manifest。
  - 新增客服／月嫂自助服務與身分管理／解除正式規格，並更新正式規格索引、裁決總表與追蹤證據。
  - 新增 merge 功能未移植 history，明確保存 query-string userId、LIFF 直接改排班及客服直接更新 client 等禁止或延後項目。

## 🔄 修改與優化檔案

- **Rich Menu 與 LIFF 預設介面**
  - 一般用戶預設選單與圖面更新為「服務登記／服務說明」等 merge 版面；月嫂選單更新為訂單及班表自助入口。
  - LINE 管理中心頁籤名稱由「LINE 下方選單」、「LINE 表單」收斂為「Rich Menu」、「LIFF 表單」。
  - 新增 fingerprint-gated Rich Menu 預設值升級工具；只有 current revision 符合已知 baseline 時才追加 canonical revision，不覆蓋人工 divergent revision。

- **Canonical LIFF 身分與首次授權流程**
  - `/line-identity` 與 `/line-identity/` 均直接回傳相同頁面，避免首次授權 primary／secondary redirect 遇到 FastAPI 307。
  - LIFF 在 `liff.init()` 完成後才讀取流程參數，並可從 `liff.state` 防禦性恢復 `purpose`、`flow_id` 與 staff target。
  - 新增 typed `/api/v1/line/identity/flow/validate` 唯讀入口；後端驗證 ID Token 後，再檢查 flow、purpose、LINE user、狀態與期限，有效才顯示表單。
  - apply 階段仍執行第二次 Domain 驗證；過期、跨使用者、錯誤用途或已失效流程不能只靠前端繞過。
  - 未填表客戶完成 provisional registration 後，保留同一 `flow_id` 續行 canonical customer identity binding，讓登記與綁定流程完整收斂。

- **資料庫與身分一致性**
  - `line_identity_bindings` 維持身分關係 SSOT；`clients`、`staff`、`admin_users` 的 LINE 欄位只作 owner projection。
  - MySQL identity repository 新增 `revocation_pending`、解除完成與 subject replacement 的 row lock、expected version、事件與冪等處理。
  - owner adapters 支援查詢、同型別對象更正及解除 projection，並在交易邊界內保存必要稽核事實。

- **Worker、能力與管理入口**
  - canonical LINE Worker 納入 identity revocation worker，並將 menu reset intent 的 next due 納入動態喚醒。
  - FastAPI 註冊 Customer Service、staff self-service 與 identity management routes；管理員認證及開發略過模式補齊新 capability projection。
  - UI 成功 payload 維持 typed view 驗證，transport／schema 錯誤轉成 typed client error，不讓 raw dict 穿透 render function。

- **專案協作規範**
  - `AGENTS.md` 新增詢問／計畫／批准／實作／驗收與 Git 操作規範；未經明確授權不得修改、migration、stage、commit 或 push，commit 前必須先更新本檔。

## 🧪 驗證結果

- Stage 11、Stage 12、LIFF entrypoint、LINE Identity Domain／Subsystem 有限測試以專案 `.venv` 執行並使用 `-W error`，既有驗證紀錄為 `41 passed`。
- 覆蓋客服狀態與回覆、月嫂本人 assignment 權限、偽造 userId 拒絕、身分更正／解除、Rich Menu-first saga、首次授權 redirect、`liff.state` context、過期流程與 HTTP typed error。
- 提交前重新執行客服、身分管理、LIFF entrypoint 與 Identity Subsystem 回歸測試，共 `38 passed`，全程使用 `-W error`。
- 未加入 `.env`、本機資料庫備份、log、monitor state 或個人簡報檔案。

## 🗑️ 刪除/重新命名檔案

- 本次沒有刪除或重新命名 production 檔案。

---
doc_type: work-package
declared_status: completed
date: 2026-08-12
owner: Global / Access Control
scope: Remove the legacy LEGACY_SHARED_KEY shared-secret mechanism from active runtime, callers, configuration, tests, and current documentation.
write_set: [api/dependencies/admin_auth.py, line/line_bot.py, start_fastapi_ngrok.py, subsystems/line/runtime_cutover.py, ui/pages/shared.py, ui/api_clients/line_api_client.py, ui/pages/07_line_management.py, ui/pages/08_system_status.py, scripts/api_contract_smoke.py, scripts/bootstrap_admin_dev_env.ps1, scripts/bootstrap_admin_dev_env.bat, online.bat, infrastructure/migration/rehearsal_runtime.py, tests, README.md, config/README_CONFIG.md, line/LINE_Bot_SOP.md, .env.example]
acceptance: Active runtime and deployment paths no longer read, require, generate, send, or validate LEGACY_SHARED_KEY or X-Legacy-Shared-Key, while existing Admin Session, capability, and LINE signature behavior remains unchanged.
out_of_scope: TOTP implementation, account-management redesign, session-policy redesign, new machine identity, unrelated authorization refactoring, production secret-store mutation, and historical archive rewriting.
---

# 71 LEGACY_SHARED_KEY Retirement Work Package

## 1. 文件狀態

- 文件類型：`work-package`
- 狀態：`completed`
- 優先級：`P1`
- 建立日期：2026-08-12
- Owner：`Global／Access Control`
- Business scenario：系統已使用既有 Admin Session、capability 與 LINE signature 處理實際存取控制，不再需要額外的全域共用 `LEGACY_SHARED_KEY`。
- 實作結果：2026-08-12 已完成 source、tests、設定與 current documentation 的範圍內移除；驗收見封存收據。

## 2. 目標

以低風險、機械式變更完整移除下列 legacy 安全機制：

- `LEGACY_SHARED_KEY` 環境變數；
- `X-Legacy-Shared-Key` HTTP header；
- internal-key resolver、validator、dependency 與自動產生邏輯；
- UI、LINE、smoke、migration rehearsal 與 startup script 對該 key 的傳遞或必要條件；
- active tests、current README、設定範例與操作文件中的現行用法。

本任務不重新設計 Access Control。既有 Admin Session、capability、development bypass 規則與 LINE webhook signature 驗證，除移除 internal-key 前置條件外，行為維持不變。

## 3. 現況與預期影響

目前 internal key 是 transport 外層的共用 secret，仍散布於 API dependency、UI client、LINE runtime、啟動腳本與測試。依現有業務流程，它不是使用者身分、角色、capability、LINE webhook 真偽或 Domain mutation 的根事實。

預期移除後：

1. 管理員登入不需要先提供 internal key。
2. 已登入管理操作仍由既有 Admin Session 與 capability 保護。
3. LINE webhook 仍由既有 LINE signature 驗證。
4. 本機與正式啟動不再要求或產生 internal key。
5. 測試與 smoke 不再組裝 legacy header。

若實作盤點發現某個 active machine caller 只有 internal key、沒有其他既有信任邊界，不在本任務內自行新增 machine identity；該 caller 標記為 blocker，從本次機械式移除中暫停並交由人工裁決。

## 4. 架構邊界

### 4.1 Global

- 移除全域 shared-secret gate。
- 不改變 actor、AdminPrincipal、Session、capability 或 audit 的 ownership。
- 不允許因刪除 key 而移除既有 route authentication dependency。

### 4.2 Domain

- 各 Domain 的根事實、狀態機、不變量與 mutation capability 不變。
- 本任務不得修改金額、日期、排班、訂單、LINE command 或其他業務規則。

### 4.3 Subsystem

- Authentication 維持既有 Session 驗證流程，只移除 internal-key 前置依賴。
- LINE ingress 維持既有 signature／identity gate。
- Migration rehearsal 與 smoke 只移除 legacy credential wiring，不改變受測場景。

### 4.4 Module／Adapter

- API 不再宣告或驗證 `X-Legacy-Shared-Key`。
- UI client 不再解析 `LEGACY_SHARED_KEY` 或附加該 header。
- startup／bootstrap 不再檢查、生成或輸出該 key。
- current configuration 不再要求部署人員設定該 secret。

## 5. Write set

已知 production／operator 範圍：

- `api/dependencies/admin_auth.py`
- `line/line_bot.py`
- `start_fastapi_ngrok.py`
- `subsystems/line/runtime_cutover.py`
- `ui/pages/shared.py`
- `ui/api_clients/line_api_client.py`
- `ui/pages/07_line_management.py`
- `ui/pages/08_system_status.py`
- `scripts/api_contract_smoke.py`
- `scripts/bootstrap_admin_dev_env.ps1`
- `scripts/bootstrap_admin_dev_env.bat`
- `online.bat`
- `infrastructure/migration/rehearsal_runtime.py`

同步範圍：

- 直接相關 tests；
- `.env.example`；
- `README.md`、`config/README_CONFIG.md`、`line/LINE_Bot_SOP.md`；
- Access Control／LINE Access 正式規格及本 Work Package evidence index。

本機 `.env` 的實際 secret 值不寫入規格、diff、測試輸出或 receipt。production secret store 的刪除屬部署操作，不由本 Work Package 的程式修改自動執行。

## 6. 實作步驟

### P0：Caller disposition

- [ ] `KEY-P0-01` fresh scan `LEGACY_SHARED_KEY`、`X-Legacy-Shared-Key`、resolver 與 header builder。
- [ ] `KEY-P0-02` 將每個 active caller 分為 Admin Session、LINE signature、local direct call、test-only 或 blocker。
- [ ] `KEY-P0-03` 確認沒有 route 因移除 key 而失去原本既有的 Session、capability 或 signature gate。

### P1：Runtime removal

- [ ] `KEY-P1-01` 移除 internal service dependency、header schema 與 key comparison。
- [ ] `KEY-P1-02` 移除 UI shared transport／LINE client 的 key resolver 與 header。
- [ ] `KEY-P1-03` 移除 LINE runtime、cutover、startup、bootstrap 與 online script 的 key requirement／generation。
- [ ] `KEY-P1-04` 移除 smoke 與 migration rehearsal 的 legacy header wiring。
- [ ] `KEY-P1-05` 不新增 fallback、placeholder key 或固定測試 secret。

### P2：Tests and contracts

- [ ] `KEY-P2-01` 將 admin auth tests 改為驗證既有 Session／capability 行為。
- [ ] `KEY-P2-02` 移除各 API／E2E fixture 的 internal-key environment 與 header。
- [ ] `KEY-P2-03` 驗證 LINE signature success／failure 行為不變。
- [ ] `KEY-P2-04` 更新 current README、設定範例、LINE SOP 與正式規格。

### P3：Closeout

- [ ] `KEY-P3-01` active source scan 對 `LEGACY_SHARED_KEY`、`X-Legacy-Shared-Key` 與 resolver 為零命中。
- [ ] `KEY-P3-02` historical archive 命中只記錄、不重寫，且不被 current entry point 引用為操作方式。
- [ ] `KEY-P3-03` 執行 focused auth、UI client、LINE、smoke 與 startup regression。
- [ ] `KEY-P3-04` 產出不含 secret 的 completion receipt，記錄測試、scan 與 blocker disposition。
- [ ] `KEY-P3-05` 部署後由 operator 從 runtime environment／secret store 移除實際 key，另留 deployment receipt。

## 7. 驗收條件

1. Active runtime source 不再讀取、要求、生成或比較 `LEGACY_SHARED_KEY`。
2. Active HTTP caller 不再送出 `X-Legacy-Shared-Key`。
3. API schema／dependency 不再宣告該 header。
4. 未登入管理 API 仍依既有 Session policy 拒絕；無 capability 仍依既有 policy 拒絕。
5. 管理員登入與已登入操作不需要 internal key。
6. LINE webhook 的合法與非法 signature 行為不變。
7. Startup、bootstrap、smoke 與 migration rehearsal 不再要求 key。
8. `.env.example` 與 current operator documents 不再要求設定 key。
9. Tests 不使用固定替代 key 模擬已移除機制。
10. Source scan 可以保留 historical archive 敘述，但 active code、current config 與 current runbook 必須零命中。

## 8. 非目標

- 不實作 TOTP、WebAuthn 或新的 MFA。
- 不重做帳號、角色、capability 或 Session 架構。
- 不新增 OAuth、service account、mTLS 或 scoped machine token。
- 不改變 LINE webhook signature、Rich Menu 或 command ownership。
- 不修改 Domain 規則、schema 或 production data。
- 不刪除歷史 decision、receipt、work log 或 archive 中的追溯文字。
- 不自動修改 production environment 或外部 secret store。

## 9. 風險與停止條件

本任務預期影響有限，主要風險是存在未盤點的外部 caller。遇到以下任一情況應停止對該 entry point 的修改並回報：

- active machine caller 唯一身分依據是 internal key；
- route 在移除 key 後沒有既有 Session、capability、signature 或其他已核准 trust boundary；
- current deployment platform 將該 key 同時用於其他系統；
- 修改範圍需要新增 public endpoint、machine identity、schema 或外部服務設定。

其他 caller 可繼續依本 Work Package 平行移除，不因單一 blocker 擴張成 Access Control 重構。

## 9.1 UI smoke observation (2026-08-12)

- Chrome UI smoke testing found no visible exception or browser console error in the
  initial workspace load, finance views, anomaly views, or operations views.
- During immediate workspace navigation, content from the previous Streamlit workspace
  was briefly rendered below the newly selected page. This may be a rerun or component
  cache lifecycle issue rather than a shared-key retirement regression.
- Before closure, repeat page navigation with up to ten seconds of settling time. Record
  whether stale content clears, and separately record any API request failure.
- This observation does not authorize data-changing UI actions. Smoke coverage may invoke
  navigation, read, and Preview only; Apply, send, create, delete, reconcile, publish,
  or other mutations require explicit operator approval.

## 10. 完成定義

只有 P0～P3 完成、focused regression 通過、active source/runtime scan 零命中、current 文件同步，且沒有未揭露 blocker 時，才能將本 Work Package 標記為 `completed`。production secret store 的實際刪除需有獨立 deployment receipt；程式完成不自動等同 production cutover 完成。

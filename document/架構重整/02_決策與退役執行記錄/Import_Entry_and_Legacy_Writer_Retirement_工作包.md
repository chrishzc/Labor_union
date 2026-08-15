---
doc_type: work-package
declared_status: blocked
priority: P1
owner: Import Integration / Global Entry Governance
domain: Finance Import / Case Import / LINE Integration
subsystem: import entrypoint transition and legacy writer retirement
initiative: import-entry-retirement
updated_date: 2026-08-15
implementation_authorization: granted-by-user-2026-08-15-for-scoped-retirement-work-packages
supersedes_scope_from: ADR-001-import-architecture-refactor
---

# 匯入入口與 Legacy Writer 退役工作包

## 1. 目的

此計畫只承接已完成的匯入架構之後，仍未收斂的入口責任：確認 Finance CLI、File Watcher 與
temporary Web／LIFF entry 是否仍為 active writer，逐項建立 replacement、retirement 或保留的
明確裁決。它不重新定義匯入資料模型、warning、historical adoption、HCM 修正或 upload lifecycle。

## 2. 現行權威與業務邊界

- `15_正式規格索引與裁決總表.md`：HCM／帳務固定 Web upload；Client／Staff BeClass 的 temporary
  authenticated Web entry 只可存在到 LIFF end-to-end 驗收完成，之後必須移除；不得回退
  File Watcher 或 browser SQL。
- `09_Finance_Import_Domain.md`、`17_External_Integration_LINE_Access正式規格.md`、
  `19_Global_Entry_Point_Governance.md`：各 owning Domain 的 typed command／API 才能寫入根事實；
  每個 API、CLI、watcher 或頁面都必須有獨立 entrypoint 裁決。
- 已封存的 WP90、WP92、WP95 與其 successor formal specs 擁有 warning、historical adoption、
  HCM owner correction 與現行 import contract；本計畫不得覆寫它們。

## 3. 實際業務場景

管理人員以核准入口上傳或提交來源資料時，每次資料只會由一個 typed owner workflow 處理；
舊 CLI／File Watcher 不得與 Web／LIFF 對同一來源形成雙 writer。若暫時保留一個維運 adapter，
它必須有明確 operator、允許來源、dry-run／idempotency、replacement 與退役期限。

## 4. 範圍與非目標

範圍：

1. 建立所有 import-related API、CLI、File Watcher、temporary Web 與 LIFF entry 的 caller inventory。
2. 對每一 entry 記錄 owning Domain、操作者、source identity、write path、replacement、退役條件與
   `19` entrypoint review queue 結果。
3. 以本計畫下的 scoped Work Package，逐項退役確定沒有業務責任的 writer，並驗證不存在雙 writer。

非目標：

- 不新增通用 `ImportFieldIssue`、row outcome、manifest、五列 upload UI 或新的 schema。
- 不修改 Finance／Case／Staff root facts、historical adoption、Anomalies registry、HCM correction 或
  upload data retention。
- 不跨越 owner／write set 直接刪除 CLI、File Watcher 或 temporary entry；每一項退役均須有本計畫
  下明確的 scoped Work Package、entrypoint 裁決與 focused regression。

## 5. 依賴、預定 write set 與驗收

依賴：現行正式 `15`、`09`、`17`、`19`，以及各被盤點入口的 owner spec。

預定 write set（取得實作授權後才可變更）：entrypoint review queue、owner route／CLI／watcher
adapter、caller inventory、focused regression 與 retirement receipt。任何 schema 或 business-root write
set 均不在本計畫授權範圍。

驗收條件：

1. 每個 active import entry 都有唯一 owner、operator 與 replacement／保留理由。
2. HCM 與 Finance 不可透過 File Watcher 或 browser SQL 寫入；temporary Client／Staff Web entry 的
   LIFF replacement 條件可機械驗證。
3. 被退役的 entry 具有 caller scan、queue disposition、focused regression 與 restore trigger。
4. 同一 source identity 不可從兩個 active writer 產生兩次 Domain mutation。

## 6. 執行 gate

每個 writer／entry 依 owner 與 write set 建立小型 Work Package；不得挾帶 schema、business-root、
外部 provider 或 temporary Web cutover。無法以 current formal contract 證明 replacement 的項目，留為
blocked，不以現況 code 取代規格裁決。

## 7. 2026-08-15 唯讀 inventory

已完成第一輪入口盤點：Finance Web API 是唯一日常寫入入口；`scripts/file_watcher.py` 雖強制 Finance
CLI dry-run，仍被 local launcher、smoke 與 candidate rehearsal 啟動，違反「帳務不得回退 File Watcher」
的正式裁決。因此已另立
`ARCH-20260815-102` 已完成並封存；其 receipt 證明 watcher、runtime caller 與 direct dependency 已移除。

HCM、Client／Staff BeClass 與 Historical Orders 不由 File Watcher 寫入；其 remaining CLI／LIFF
cutover／legacy SQL 責任必須各自分包，不能與本次 Finance watcher 退役合併。

## 8. 2026-08-15 已完成切片

- `ARCH-20260815-102`：Finance File Watcher 已退役；Finance Web upload 保持唯一日常入口。
- `ARCH-20260815-103`：已移除 `scripts/import_historical_orders.py` 的 retired CLI 與殘留 direct SQL；
  Orders typed Web 和受控 `adopt_historical_orders.py` 保留。
- `ARCH-20260815-104`：Finance CLI `--apply` 已 fail closed；CLI 僅保留 operator-only format diagnostic，
  authenticated Finance Web API 是唯一日常寫入入口。
- `ARCH-20260815-105`：已移除 HCM legacy CLI entrypoint；HCM typed Web 保留 shared adapter，historical
  whole-row overwrite routes 維持退役。
- `ARCH-20260815-106`：已移除 HCM historical service composition 與 whole-row direct SQL writer。
- `scripts/imports/reprocess_finance_import_batch.py` 的 apply 原已在 DB connection 前拒絕，保留其
  read-only diagnostic，不另作退役。

## 9. 剩餘工作與阻塞

1. **Client／Staff BeClass dead SQL**：可在各自 owner Work Package 中移除不可達 legacy helper，但先要
   重查受控 historical CLI 的維運責任與 tests；不可把歷史 intake 當成 current LIFF writer。
3. **Client temporary Web → LIFF**：blocked，需真實 LIFF ID token、registration replay、Rich Menu
   binding／publication的 end-to-end acceptance；未驗收前 Web 不得退役。
4. **Staff current LIFF writer**：blocked，正式規格尚未裁決 Staff profile root owner、欄位、version、
   UoW 與 typed error；LINE identity bind 不是 profile writer replacement。

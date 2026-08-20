---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Finance Import / Global Entry Governance
domain: Finance Import
subsystem: Local runtime and legacy entrypoint retirement
implementation_authorization: granted-by-user-2026-08-15
---

# Finance File Watcher 退役工作包

## 1. 業務場景與裁決

銀行檔案的日常寫入只能從 authenticated Finance Web upload 進入 Finance Import typed workflow；
本機開發啟動、candidate rehearsal 或監看資料夾不得再提供「將檔案放入資料夾即可處理」的
File Watcher 入口。此裁決依正式 `15` 的「帳務固定 Web upload，不得回退 File Watcher」規則。

## 2. Scope 與 write set

本包只退役 `scripts/file_watcher.py` 與它的 direct callers：

- `scripts/launchers/start_local_development.bat`／`.sh`
- `scripts/smoke_local_development_launcher.py`
- `infrastructure/migration/rehearsal_runtime.py`
- File Watcher 專屬測試、entrypoint queue、script map 與無其他使用者的 `watchdog` dependency。

不改 Finance API、Finance Import Domain、資料庫、batch／idempotency、CLI `import_finance_excel.py` 的
`--apply`，也不處理 HCM、BeClass、Staff 或 historical Orders CLI。這些屬不同 owner／write set，
由 `Import_Entry_and_Legacy_Writer_Retirement_開發計畫.md` 後續分包。

## 3. 交易與外部副作用

本包不執行匯入、不寫入資料庫、不啟動服務、不操作 Task Scheduler 或外部 provider。唯一行為改變是
移除 local runtime 對 File Watcher process 的啟動；既有 Finance Web API 是唯一 replacement。

## 4. 驗收

1. 專案不再有 `scripts/file_watcher.py` 或任何 runtime caller／launcher target。
2. File Watcher 不再出現在 current entrypoint queue；本工作包保留退役決策與 Finance Web ingestion
   replacement，符合 queue 僅列可發現 current entry 的 validator 契約。
3. `watchdog` 不再是 direct dependency，lockfile 同步。
4. local launcher、candidate rehearsal 與 entrypoint queue focused tests 均通過；`git diff --check` 通過。

## 5. 完成後責任

完成後更新本工作包 evidence 與 `Import_Entry_and_Legacy_Writer_Retirement_開發計畫.md`。不得將
Finance CLI 寫入旗標、temporary Web／LIFF cutover、legacy HCM／BeClass direct SQL 或 historical
Orders dead code 偷渡進本包。

## 6. 完成證據

2026-08-15 已移除 File Watcher source、local launcher、smoke 與 candidate rehearsal caller；
`watchdog` direct dependency 與 current entrypoint queue 項目也已同步移除。驗收收據：
`../03_追蹤清單與證據/evidence/finance_file_watcher_retirement_receipt_20260815.md`。

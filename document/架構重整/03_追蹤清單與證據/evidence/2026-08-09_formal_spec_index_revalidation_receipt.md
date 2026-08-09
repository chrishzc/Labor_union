---
scope: 15_正式規格索引與裁決總表
status: reconciled-current-evidence
verified_at: 2026-08-09
---

# 正式規格索引與裁決總表重新驗證收據

## 裁決與實作比對

- 第 15 份規格是 15～18 正式架構基線的權威順序、Domain ownership、跨域不變量與
  衝突裁決入口；它不另行授權業務金額、狀態或 migration 實作。
- 現行實作授權由後續已核准 decision／work package 管理。`46` 已對齊決策 53：target-host
  deployment acceptance 退役；`51` 管理 preserve-data 與 Historical Reprocess 的本機收斂。
  這些後續決策均未推翻第 15 份的 Global ownership、outer Unit of Work、typed command 與
  Streamlit thin-adapter 邊界。
- `architecture_approval_2026-08-03.json` 是 2026-08-03 原始人工核准的歷史收據，其 package
  SHA 不因本次索引路徑校正而改寫。

## 修正的證據漂移

第 15 份仍指向不存在的 `document/架構重整/evidence/`。核准收據與 Inventory v2 artifact 的
受管理位置實為 `document/架構重整/03_追蹤清單與證據/evidence/`，索引現已同步到該位置。
這是文件索引修正，沒有變更架構語意、production code、schema、資料或外部系統。

一般客戶退款原先仍標示 `partial`，但第 16 份的現行收據、後續決策與退款／退匯／匯出
分層測試均已證實其正式能力完成，索引已改為目前 evidence。deployment profile／target-host
acceptance 的舊裁決也已替換為決策 53 的退役狀態。

## 驗收

`tests/test_formal_spec_index_evidence_paths.py` 驗證正式索引不再引用舊 evidence 根目錄，且
目前核准收據與 Inventory v2 README 均存在於受管理證據目錄。

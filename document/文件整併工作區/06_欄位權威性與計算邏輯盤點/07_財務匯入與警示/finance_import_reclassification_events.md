# `finance_import_reclassification_events` 退役紀錄

- 狀態：已自「欄位權威性與計算邏輯盤點」移除；不是現行資料模型或 SSOT。
- 原 Schema：`db/schema_parts/61_finance_import_reprocessing.sql` 的舊 16 欄 append-only audit table。
- 退役依據：正式 runtime 已改由 `HistoricalReprocessWorkflow` 寫入 `finance_import_classification_events`、`finance_import_historical_reprocess_receipts` 與（需要人工指定時）`historical_owner_selection_events`。程式碼沒有 `finance_import_reclassification_events` 的 production writer 或 reader。
- 資料保留：來源 preservation rehearsal 的此表為 0 筆；目前本機 candidate 已直接 drop，且 `153_retire_empty_legacy_field_inventory.sql` 會在後續 bootstrap／candidate upgrade 移除它。舊 preservation dump 僅是歷史證據，不得當成可重新啟用的相容介面。
- 裁決：16 個 `before_*`／`after_*`、dispatch 與關聯欄位不再列為欄位權威性；新的分類與處置必須讀取上列 canonical events／receipt，不得新增 writer。

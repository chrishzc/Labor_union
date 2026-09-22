# UI 驗收資料集

本目錄保留版本化 fixture、預期根事實與歷史情境資料；不提供獨立的資料庫建立、seed 或 readback 操作命令。先前要求 `lu_test_dataset_*` 的命令已移除，不應改用正式庫或僅刪除名稱檢查來執行。

仍被測試匯入的 dataset helpers 保留原有目標檢查及 owner workflow 呼叫。`tests/test_validation_dataset_scripts.py` 驗證 intent、fixture 契約、目標限制、重播與組合行為；函式庫清單及實際 CI 範圍見 [scripts_map.md](../../scripts/scripts_map.md)。

`dataset_v1_foundation.json` 中的預期值是該 fixture 的契約，不表示目前 UI 已驗收，也不是一般使用者的資料庫狀態。舊 Streamlit 頁面名稱及固定批次 ID 的操作指示已移除。歷史 receipts 保留其原始內容；需要已移除 runner 的情境在現行宣告中標示 `blocked`，不重寫舊證據為本次通過。

# 歷史文件復原入口

已完成、已取代的 Work Package、舊規格、release record 與結案 receipt 已於 2026-08-29
自目前工作樹移除，避免日常任務把低頻歷史資料載入上下文。

需要 incident、rollback、migration lineage、舊 release 重現或稽核時，請從移除前的 Git
commit `5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65` 精準取回單一檔案；不要還原整個 archive。
現行契約仍以 `../01_規格基線/`、`../02_決策與退役執行記錄/`、
`../03_追蹤清單與證據/`、`validation/` 與 production code 為準。

本次只移除 Git 工作樹中的低頻副本，沒有刪除 Git 歷史、現行 validation assets、schema、
production data 或 release artifacts。

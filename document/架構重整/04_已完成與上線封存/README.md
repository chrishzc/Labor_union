# 歷史文件復原入口

已完成、已取代且沒有 current consumer 的 Work Package、舊規格、計畫、progress／handoff receipt與歷史盤點，不在目前工作樹維持第二份 archive；Git歷史就是封存層。日常任務只使用 current spec、current successor與必要 aggregate evidence。

## 復原基準

- 2026-08-29 第一批歷史收斂前基準：`5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65`
- 2026-09-01 文件清理第一批前基準：`1f7c9cd7d90895f7846333c48cdb37c95da4caad`

需要 incident、rollback、migration lineage、舊 release重現或稽核時，應從適用的基準commit精準取回單一檔案；不要還原整個archive，也不要把歷史文件重新升格為current SSOT或施工gate。

2026-09-01第一批移除範圍限於：

- 已完成且自帶刪除條件的Task 97 pre-slimming report；
- 已由aggregate integration receipt承接的Anomalies來源lane receipt；
- Task 96 spec-ready、handoff與已關閉defect的中間receipt。

本清理不刪除Git歷史、current formal specs、source、tests、validation canonical assets、schema、migration release、production data或外部artifact。現行契約與工作邊界仍以`../01_規格基線/`、必要的`../02_決策與退役執行記錄/`、`../03_追蹤清單與證據/`、`validation/`及production code為準。

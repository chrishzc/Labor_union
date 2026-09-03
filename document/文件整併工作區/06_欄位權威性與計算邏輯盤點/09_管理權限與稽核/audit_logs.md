# `audit_logs` 退役紀錄

- 狀態：已自欄位權威清冊與新建 schema 移除。
- 退役依據：原 Data Browser 單列 PATCH 已退役為 HTTP 410；舊 writer 模組不再存在，沒有 production reader。保留資料演練中的本表為空。
- 正式替代：一般管理命令稽核由 `admin_audit_logs` 承擔；它與受驗證管理員 principal、request metadata 和保留期限政策相連。資料修正必須走 owning Domain 的 typed Preview/Apply，不得回復通用資料列 PATCH。
- 裁決：`id`、`action`、`table_name`、`pk_value`、`changed_fields`、`actor`、`role`、`request_id`、`before_hash`、`after_hash`、`changed_fields_hash`、`occurred_at` 均不再具有欄位權威性。目前本機 candidate 的空實體表已直接 drop。

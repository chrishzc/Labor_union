# `faq` 退役紀錄

- 狀態：已自欄位權威清冊與新建 schema 移除。
- 退役依據：沒有 production writer／reader、Data Browser 白名單或保留資料；preservation rehearsal 顯示本表為空。
- 正式替代：`knowledge_items` 是受審核、版本化、可發布的內容根事實；`knowledge_item_events` 保存審核／發布事件；`knowledge_apply_receipts` 保存 Apply 冪等收據。LINE 僅讀已發布的 Retrieval read model。
- 裁決：`id`、`question`、`answer`、`created_at`、`updated_at` 不再有欄位權威性；不得重建舊 FAQ writer 或把未審核文字直接當 LINE 回覆來源。目前本機 candidate 的空表已直接 drop。

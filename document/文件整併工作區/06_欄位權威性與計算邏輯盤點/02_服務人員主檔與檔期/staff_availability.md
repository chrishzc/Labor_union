# `staff_availability` 退役紀錄

- 狀態：已自欄位權威清冊與新建 schema 移除。
- 退役依據：`id`、`staff_id`、`start_date`、`end_date`、`created_at`、`updated_at` 都沒有正式 writer／reader；它只表達過於粗略的區間，無法處理多人指派、請假替班、有效 generation 或跨案衝突。
- 正式替代：可服務性由 `caregiver_availability_locks` 控制，實際佔用與服務日由 `staff_schedule`／Scheduling Domain 的有效 generation 決定。
- 裁決：不得重建此表或以 `start_date`／`end_date` 作排班與媒合依據。目前本機 candidate 的空實體表已直接 drop。

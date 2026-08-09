# `crawler_logs` 退役紀錄

- 狀態：已自欄位權威清冊與新建 schema 移除。
- 退役依據：沒有 production writer／reader，preservation rehearsal 顯示本表為空；它沒有 batch identity、來源事實、明細關聯或受控錯誤契約，不能作為任何 Pipeline 的稽核依據。
- 裁決：`id`、`crawled_at`、`status`、`records_inserted`、`records_updated`、`message` 不再有欄位權威性。未來若實作 BeClass／HCM 等匯入監控，必須隨實際 workflow 建立有 command identity、來源、明細及 retry 語意的專用事件／receipt，不得重用此通用表。
- 資料保留：目前本機 candidate 的空實體表已直接 drop。

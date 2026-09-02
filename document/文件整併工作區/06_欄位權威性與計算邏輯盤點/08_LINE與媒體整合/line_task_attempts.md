# Table: line_task_attempts

> LINE 功能續盤：跳過待確認；等待 LINE API 接通與實際測試後重新核對。既有明確裁決保留，不視為撤銷。

## 1. 核心定位與職責
- 領域分類：08_LINE與媒體整合
- 類型：事件表 (Event)
- 已確認跨表裁決：記錄 line_tasks 每次發送的嘗試與錯誤。

## 2. 欄位權威性與計算邏輯

| 欄位名稱 | 型態與約束 | 業務定義 | 權威性 | 計算邏輯 / 公式 | 寫入時機 / 來源 | 驗證規則 | 鎖定與快照機制 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| id | BIGINT AUTO_INCREMENT PK | 流水號。 | 系統生成 | 無。 | 每次重試發送。 | 無。 | 無。 | 已確認 |
| task_id | BIGINT NOT NULL | 對應的 Task ID。 | 外鍵 | 無。 | 重試建立。 | 必須存在 line_tasks。 | 不可變。 | 已確認 |
| attempt_no | INT NOT NULL | 嘗試次數。 | 系統生成 | 無。 | 發送時遞增。 | 無。 | 無。 | 已確認 |
| outcome | ENUM(...) NOT NULL | 執行結果。 | 狀態更新 | 無。 | API 回傳或超時。 | 必須是合法列舉。 | 完成後不可變。 | 已確認 |
| retryable | BOOLEAN NULL | 是否可重試。 | 衍生計算 | API 錯誤碼判定。 | 失敗時寫入。 | 無。 | 無。 | 已確認 |
| error_code | VARCHAR(100) NULL | 錯誤代碼。 | 來源事實 | 無。 | API 回傳。 | 無。 | 無。 | 已確認 |
| error_message | TEXT NULL | 錯誤訊息。 | 來源事實 | 無。 | API 回傳。 | 無。 | 無。 | 已確認 |
| line_request_id | VARCHAR(100) NULL | 請求 ID。 | 來源事實 | 無。 | API 回傳。 | 無。 | 無。 | 已確認 |
| started_at | DATETIME NOT NULL | 開始時間。 | 系統生成 | 無。 | 嘗試發起時。 | 無。 | 無。 | 已確認 |
| finished_at | DATETIME NULL | 結束時間。 | 系統生成 | 無。 | 嘗試結束時。 | 無。 | 無。 | 已確認 |

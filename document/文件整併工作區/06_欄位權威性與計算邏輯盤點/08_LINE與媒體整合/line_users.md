# Table: line_users

> LINE 功能續盤：跳過待確認；等待 LINE API 接通與實際測試後重新核對。既有明確裁決保留，不視為撤銷。

## 1. 核心定位與職責
- 領域分類：08_LINE與媒體整合
- 類型：事實表 (Fact)
- 已確認跨表裁決：本表為 **LINE 綁定與使用者帳號的核心樞紐**。所有與 LINE 溝通的身份識別皆以此表的 line_user_id 為主鍵。

## 2. 欄位權威性與計算邏輯

| 欄位名稱 | 型態與約束 | 業務定義 | 權威性 | 計算邏輯 / 公式 | 寫入時機 / 來源 | 驗證規則 | 鎖定與快照機制 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| id | BIGINT AUTO_INCREMENT PK | 內部流水號。 | 系統生成 | 無。 | 首次互動。 | 必須唯一。 | 無。 | 已確認 |
| line_user_id | VARCHAR(100) NOT NULL | LINE UID。 | 來源事實 | 無。 | 用戶加入官方帳號或綁定。 | LINE API 驗證。 | 綁定後不變。 | 已確認 |
| role | ENUM(...) NOT NULL | 使用者角色 (客戶/月嫂)。 | 來源事實 | 無。 | 審核或綁定時決定。 | 必須是合法列舉。 | 無。 | 已確認 |
| status | ENUM(...) NOT NULL | 帳號狀態 (有效/封鎖)。 | 來源事實 | 無。 | 系統或 webhook 觸發。 | 必須是合法列舉。 | 無。 | 已確認 |
| followed_at | DATETIME NULL | 加入好友時間。 | 來源事實 | 無。 | Webhook 觸發。 | 無。 | 無。 | 已確認 |
| blocked_at | DATETIME NULL | 封鎖時間。 | 來源事實 | 無。 | Webhook 觸發。 | 無。 | 無。 | 已確認 |
| last_event_at | DATETIME NULL | 最後互動時間。 | 狀態更新 | 無。 | 任何有效 webhook。 | 無。 | 無。 | 已確認 |
| onboarding_started_at | DATETIME NULL | 註冊開始時間。 | 狀態更新 | 無。 | 啟動綁定。 | 無。 | 無。 | 已確認 |
| onboarding_completed_at | DATETIME NULL | 註冊完成時間。 | 狀態更新 | 無。 | 完成綁定。 | 無。 | 無。 | 已確認 |

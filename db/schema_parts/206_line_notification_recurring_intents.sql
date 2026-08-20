-- File: 206_line_notification_recurring_intents.sql
-- Description: 讓同一通知決策可保存受規則上限約束的多次每日提醒意圖。

ALTER TABLE line_notification_intents
    ADD COLUMN occurrence_number INT UNSIGNED NOT NULL DEFAULT 1 AFTER decision_id,
    DROP INDEX uq_line_notification_intent_decision,
    ADD UNIQUE KEY uq_line_notification_intent_decision_occurrence (decision_id, occurrence_number);

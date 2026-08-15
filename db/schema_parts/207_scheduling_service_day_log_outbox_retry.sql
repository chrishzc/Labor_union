-- File: 207_scheduling_service_day_log_outbox_retry.sql
-- Description: 為服務日日誌完成 outbox 加入一秒間隔、最多三次的可恢復投影時點。

ALTER TABLE scheduling_service_day_log_outbox
    ADD COLUMN next_attempt_at_utc DATETIME(6) NULL AFTER attempt_count,
    ADD INDEX idx_scheduling_service_day_log_outbox_retry (delivery_status, next_attempt_at_utc, id);

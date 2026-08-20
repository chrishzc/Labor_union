-- File: 208_scheduling_rebuild_notification_invalidation.sql
-- Description: 將排班重建的已取消指派以不可變 outbox 提供 LINE 取消尚未送出的舊提醒。

CREATE TABLE IF NOT EXISTS scheduling_rebuild_notification_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rebuild_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    delivery_status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    published_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_rebuild_notification_outbox_event (rebuild_event_id),
    UNIQUE KEY uq_scheduling_rebuild_notification_outbox_intent (intent_key),
    INDEX idx_scheduling_rebuild_notification_outbox_delivery (delivery_status,next_attempt_at_utc,id),
    CONSTRAINT fk_scheduling_rebuild_notification_outbox_event FOREIGN KEY (rebuild_event_id)
        REFERENCES scheduling_rebuild_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_rebuild_notification_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- File: 204_scheduling_service_day_logs.sql
-- Description: 新增月嫂服務日寶寶日誌、餐食照片關聯、完成事件與通知用 Scheduling outbox。

CREATE TABLE IF NOT EXISTS scheduling_service_day_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    staff_line_user_id VARCHAR(191) NOT NULL,
    service_date DATE NOT NULL,
    baby_log_text TEXT NOT NULL,
    requires_cooking BOOLEAN NOT NULL,
    content_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_assignment_date (assignment_id, service_date),
    UNIQUE KEY uq_scheduling_service_day_log_idempotency (idempotency_key),
    INDEX idx_scheduling_service_day_log_case_date (case_no, service_date, id),
    CONSTRAINT fk_scheduling_service_day_log_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_log_text CHECK (CHAR_LENGTH(TRIM(baby_log_text)) > 0),
    CONSTRAINT chk_scheduling_service_day_log_fingerprint CHECK (content_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_log_attachments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    service_day_log_id BIGINT UNSIGNED NOT NULL,
    provider_media_id VARCHAR(191) NOT NULL,
    attachment_kind ENUM('meal_photo') NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_attachment (service_day_log_id, provider_media_id),
    CONSTRAINT fk_scheduling_service_day_log_attachment_root FOREIGN KEY (service_day_log_id) REFERENCES scheduling_service_day_logs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_attachment_media FOREIGN KEY (provider_media_id) REFERENCES line_media_records(provider_media_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_log_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    service_day_log_id BIGINT UNSIGNED NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_date DATE NOT NULL,
    event_type ENUM('submitted') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_event_root (service_day_log_id, event_type),
    UNIQUE KEY uq_scheduling_service_day_log_event_idempotency (idempotency_key),
    INDEX idx_scheduling_service_day_log_event_assignment_date (assignment_id, service_date, id),
    CONSTRAINT fk_scheduling_service_day_log_event_root FOREIGN KEY (service_day_log_id) REFERENCES scheduling_service_day_logs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_event_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_log_event_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_log_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    delivery_status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    published_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_log_outbox_event (event_id),
    UNIQUE KEY uq_scheduling_service_day_log_outbox_intent (intent_key),
    INDEX idx_scheduling_service_day_log_outbox_delivery (delivery_status, created_at_utc, id),
    CONSTRAINT fk_scheduling_service_day_log_outbox_event FOREIGN KEY (event_id) REFERENCES scheduling_service_day_log_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_log_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_scheduling_service_day_log_attachments_before_update
BEFORE UPDATE ON scheduling_service_day_log_attachments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_attachments cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_log_attachments_before_delete
BEFORE DELETE ON scheduling_service_day_log_attachments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_attachments cannot be deleted';

CREATE TRIGGER trg_scheduling_service_day_log_events_before_update
BEFORE UPDATE ON scheduling_service_day_log_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_events cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_log_events_before_delete
BEFORE DELETE ON scheduling_service_day_log_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_events cannot be deleted';

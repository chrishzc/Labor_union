-- File: 205_scheduling_service_day_checkpoints.sql
-- Description: 為已結束的正式服務日保存不可變 checkpoint 與 outbox，供 LINE 規則安全判斷寶寶日誌是否逾期。

CREATE TABLE IF NOT EXISTS scheduling_service_day_checkpoints (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    schedule_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_date DATE NOT NULL,
    service_ends_at_utc DATETIME(6) NOT NULL,
    requires_cooking BOOLEAN NOT NULL,
    baby_log_completed BOOLEAN NOT NULL DEFAULT FALSE,
    checkpoint_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_assignment_date (assignment_id, service_date),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_key (checkpoint_key),
    INDEX idx_scheduling_service_day_checkpoint_due (service_ends_at_utc, id),
    CONSTRAINT fk_scheduling_service_day_checkpoint_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_checkpoint_assignment FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_service_day_checkpoint_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_checkpoint_key CHECK (CHAR_LENGTH(TRIM(checkpoint_key)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_checkpoint_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    checkpoint_id BIGINT UNSIGNED NOT NULL,
    event_type ENUM('service_ended') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_event_root (checkpoint_id, event_type),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_event_idempotency (idempotency_key),
    CONSTRAINT fk_scheduling_service_day_checkpoint_event_root FOREIGN KEY (checkpoint_id) REFERENCES scheduling_service_day_checkpoints(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_day_checkpoint_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    delivery_status ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    published_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_outbox_event (event_id),
    UNIQUE KEY uq_scheduling_service_day_checkpoint_outbox_intent (intent_key),
    INDEX idx_scheduling_service_day_checkpoint_outbox_delivery (delivery_status, next_attempt_at_utc, id),
    CONSTRAINT fk_scheduling_service_day_checkpoint_outbox_event FOREIGN KEY (event_id) REFERENCES scheduling_service_day_checkpoint_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_service_day_checkpoint_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_scheduling_service_day_checkpoints_before_update
BEFORE UPDATE ON scheduling_service_day_checkpoints
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoints cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_checkpoints_before_delete
BEFORE DELETE ON scheduling_service_day_checkpoints
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoints cannot be deleted';

CREATE TRIGGER trg_scheduling_service_day_checkpoint_events_before_update
BEFORE UPDATE ON scheduling_service_day_checkpoint_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoint_events cannot be updated';

CREATE TRIGGER trg_scheduling_service_day_checkpoint_events_before_delete
BEFORE DELETE ON scheduling_service_day_checkpoint_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoint_events cannot be deleted';

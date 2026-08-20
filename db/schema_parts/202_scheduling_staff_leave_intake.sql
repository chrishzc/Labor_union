-- File: 202_scheduling_staff_leave_intake.sql
-- Description: 新增月嫂 LINE 請假待辦的版本化根事實、事件、receipt 與正式排班關聯。

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_aggregates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    leave_start_date DATE NOT NULL,
    leave_end_date DATE NOT NULL,
    request_reason VARCHAR(1000) NOT NULL DEFAULT '',
    request_status ENUM('pending','accepted_for_processing','rejected','cancelled','resolved') NOT NULL,
    aggregate_version INT UNSIGNED NOT NULL DEFAULT 1,
    request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_request_fingerprint (staff_id, request_fingerprint),
    INDEX idx_staff_leave_request_queue (request_status, created_at, id),
    CONSTRAINT fk_staff_leave_request_staff FOREIGN KEY (staff_id) REFERENCES staff(id),
    CONSTRAINT chk_staff_leave_request_dates CHECK (leave_start_date <= leave_end_date),
    CONSTRAINT chk_staff_leave_request_fingerprint CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT NOT NULL,
    aggregate_version INT UNSIGNED NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(1000) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_request_event_version (request_id, aggregate_version),
    CONSTRAINT fk_staff_leave_request_event_root FOREIGN KEY (request_id) REFERENCES scheduling_staff_leave_request_aggregates(id),
    CONSTRAINT chk_staff_leave_request_event_text CHECK (CHAR_LENGTH(TRIM(event_type)) > 0 AND CHAR_LENGTH(TRIM(actor_id)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    request_id BIGINT NOT NULL,
    request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_request_receipt_key (idempotency_key),
    CONSTRAINT fk_staff_leave_request_receipt_root FOREIGN KEY (request_id) REFERENCES scheduling_staff_leave_request_aggregates(id),
    CONSTRAINT chk_staff_leave_request_receipt_fingerprint CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_staff_leave_request_receipt_snapshot CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_leave_request_resolution_links (
    request_id BIGINT PRIMARY KEY,
    leave_substitution_receipt_key VARCHAR(191) NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_leave_resolution_receipt (leave_substitution_receipt_key),
    CONSTRAINT fk_staff_leave_resolution_root FOREIGN KEY (request_id) REFERENCES scheduling_staff_leave_request_aggregates(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_staff_leave_request_events_before_update
BEFORE UPDATE ON scheduling_staff_leave_request_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_events cannot be updated';

CREATE TRIGGER trg_staff_leave_request_events_before_delete
BEFORE DELETE ON scheduling_staff_leave_request_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_events cannot be deleted';

CREATE TRIGGER trg_staff_leave_request_receipts_before_update
BEFORE UPDATE ON scheduling_staff_leave_request_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_receipts cannot be updated';

CREATE TRIGGER trg_staff_leave_request_receipts_before_delete
BEFORE DELETE ON scheduling_staff_leave_request_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_receipts cannot be deleted';

CREATE TRIGGER trg_staff_leave_resolution_links_before_update
BEFORE UPDATE ON scheduling_staff_leave_request_resolution_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_resolution_links cannot be updated';

CREATE TRIGGER trg_staff_leave_resolution_links_before_delete
BEFORE DELETE ON scheduling_staff_leave_request_resolution_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_resolution_links cannot be deleted';

-- File: 1000_staff_retirement.sql
-- Description: Staff lifecycle state、不可變事件與冪等 receipt。

CREATE TABLE IF NOT EXISTS staff_lifecycle_states (
    staff_id INT NOT NULL PRIMARY KEY,
    lifecycle_state ENUM('active','retired') NOT NULL DEFAULT 'active',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    effective_at DATETIME(6) NULL,
    reason_code VARCHAR(64) NULL,
    updated_by VARCHAR(100) NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_lifecycle_state_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_lifecycle_state_version CHECK (aggregate_version >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_lifecycle_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    event_type ENUM('retired','reactivated') NOT NULL,
    before_state ENUM('active','retired') NOT NULL,
    resulting_state ENUM('active','retired') NOT NULL,
    effective_at DATETIME(6) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_lifecycle_event_version (staff_id, resulting_version),
    INDEX idx_staff_lifecycle_event_time (staff_id, effective_at),
    CONSTRAINT fk_staff_lifecycle_event_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_lifecycle_event_version CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_lifecycle_apply_receipts (
    idempotency_key VARCHAR(191) NOT NULL PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    resulting_state ENUM('active','retired') NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    event_id BIGINT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_lifecycle_receipt_staff FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_lifecycle_receipt_event FOREIGN KEY (event_id) REFERENCES staff_lifecycle_events(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

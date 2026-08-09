-- Canonical LINE runtime leases, worker heartbeat, and webhook security facts.
-- This migration is additive and preserves every Stage 2 and legacy row.

ALTER TABLE line_inbox_events
    MODIFY processing_status ENUM(
        'pending','processing','processed','ignored',
        'retryable_failed','terminal_failed'
    ) NOT NULL DEFAULT 'pending';

CREATE TABLE IF NOT EXISTS line_worker_heartbeats (
    worker_identity VARCHAR(191) PRIMARY KEY,
    process_id INT UNSIGNED NOT NULL,
    host_name VARCHAR(191) NOT NULL,
    runtime_mode ENUM('legacy','canonical','compatibility') NOT NULL,
    component_status_snapshot JSON NOT NULL,
    last_cycle_at_utc DATETIME(6) NULL,
    heartbeat_at_utc DATETIME(6) NOT NULL,
    stopped_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(191) NULL,
    last_error_message VARCHAR(1000) NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_worker_heartbeat (heartbeat_at_utc, stopped_at_utc),
    CONSTRAINT chk_line_worker_components
        CHECK (JSON_TYPE(component_status_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_webhook_security_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    request_fingerprint CHAR(64) NOT NULL,
    signature_present BOOLEAN NOT NULL,
    verification_outcome ENUM(
        'verified','invalid_signature','invalid_payload','storage_failed'
    ) NOT NULL,
    event_count INT UNSIGNED NOT NULL DEFAULT 0,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_line_webhook_security_outcome (
        verification_outcome, occurred_at_utc, id
    ),
    INDEX idx_line_webhook_security_fingerprint (request_fingerprint, id),
    CONSTRAINT chk_line_webhook_security_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_webhook_security_receipts_before_update;
CREATE TRIGGER trg_line_webhook_security_receipts_before_update
BEFORE UPDATE ON line_webhook_security_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_webhook_security_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_webhook_security_receipts_before_delete;
CREATE TRIGGER trg_line_webhook_security_receipts_before_delete
BEFORE DELETE ON line_webhook_security_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_webhook_security_receipts records cannot be deleted';

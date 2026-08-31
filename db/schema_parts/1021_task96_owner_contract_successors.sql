-- File: 1021_task96_owner_contract_successors.sql
-- Purpose: additive persistence for the approved Client Profile owner successor.
-- Data effect: schema only. Existing business rows are neither inferred nor rewritten.

ALTER TABLE clients
    ADD COLUMN client_profile_version BIGINT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE client_profile_change_requests
    MODIFY COLUMN status ENUM(
        'pending','approved','approved_applied','partially_approved','rejected','reverted'
    ) NOT NULL DEFAULT 'pending',
    ADD COLUMN request_version BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER status,
    ADD COLUMN client_profile_version BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER request_version,
    ADD COLUMN reason VARCHAR(500) NULL AFTER old_values_json,
    ADD COLUMN idempotency_key VARCHAR(191) NULL AFTER reason,
    ADD COLUMN preview_fingerprint CHAR(64) NULL AFTER idempotency_key,
    ADD COLUMN command_fingerprint CHAR(64) NULL AFTER preview_fingerprint,
    ADD COLUMN correlation_id VARCHAR(191) NULL AFTER command_fingerprint,
    ADD COLUMN review_reason VARCHAR(500) NULL AFTER rejection_reason,
    ADD UNIQUE KEY uq_client_profile_change_request_idempotency (idempotency_key),
    ADD CONSTRAINT chk_client_profile_change_request_fingerprints CHECK (
        (preview_fingerprint IS NULL OR preview_fingerprint REGEXP '^[0-9a-f]{64}$')
        AND (command_fingerprint IS NULL OR command_fingerprint REGEXP '^[0-9a-f]{64}$')
    );

CREATE TABLE IF NOT EXISTS client_profile_change_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT NOT NULL,
    client_id INT NOT NULL,
    event_type ENUM('approved_applied','rejected') NOT NULL,
    resulting_profile_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_values_json JSON NOT NULL,
    after_values_json JSON NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_profile_change_event_key (idempotency_key),
    INDEX idx_client_profile_change_event_request (request_id,id),
    CONSTRAINT fk_client_profile_change_event_request FOREIGN KEY (request_id)
        REFERENCES client_profile_change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_profile_change_event_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_profile_change_event_payload CHECK (
        JSON_TYPE(before_values_json)='OBJECT' AND JSON_TYPE(after_values_json)='OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_profile_change_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_client_profile_change_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_client_profile_change_receipt_result CHECK (JSON_TYPE(result_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_profile_change_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT NOT NULL,
    event_type ENUM('client_profile.approved') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    payload_json JSON NOT NULL,
    status ENUM('pending','processing','delivered','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at_utc DATETIME NULL,
    last_error_code VARCHAR(100) NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_profile_change_outbox_key (idempotency_key,event_type),
    INDEX idx_client_profile_change_outbox_due (status,next_attempt_at_utc,id),
    CONSTRAINT fk_client_profile_change_outbox_request FOREIGN KEY (request_id)
        REFERENCES client_profile_change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_profile_change_outbox_payload CHECK (JSON_TYPE(payload_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_profile_change_events_before_update;
CREATE TRIGGER trg_client_profile_change_events_before_update BEFORE UPDATE ON client_profile_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client profile change events cannot be updated';
DROP TRIGGER IF EXISTS trg_client_profile_change_events_before_delete;
CREATE TRIGGER trg_client_profile_change_events_before_delete BEFORE DELETE ON client_profile_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client profile change events cannot be deleted';

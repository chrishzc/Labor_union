-- File: 1023_task96_line_safe_review_link_matching_outbox_v1.sql
-- Purpose: additive LINE safe-review-link roots and M3 owner-intent successor.
-- Data effect: schema only; existing matching outbox rows remain readable.

ALTER TABLE matching_coordination_outbox
    MODIFY COLUMN intent_type ENUM(
        'line_matching_interaction','line_criteria_diff_resend',
        'assignment_conversion_requested','rematch_requested',
        'orders_terms_update_requested','line_bilateral_notification',
        'line_client_decision','customer_service_ticket'
    ) NOT NULL,
    MODIFY COLUMN target_owner ENUM(
        'line_integration','assignment_workflow','orders_workflow',
        'customer_service'
    ) NOT NULL,
    DROP CHECK chk_matching_outbox_target,
    ADD CONSTRAINT chk_matching_outbox_target CHECK (
        (intent_type IN (
            'line_matching_interaction','line_criteria_diff_resend',
            'line_bilateral_notification','line_client_decision'
        ) AND target_owner = 'line_integration')
        OR (intent_type IN ('assignment_conversion_requested','rematch_requested')
            AND target_owner = 'assignment_workflow')
        OR (intent_type = 'orders_terms_update_requested'
            AND target_owner = 'orders_workflow')
        OR (intent_type = 'customer_service_ticket'
            AND target_owner = 'customer_service')
    );

CREATE TABLE IF NOT EXISTS line_safe_review_links (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    link_id VARCHAR(191) NOT NULL,
    token_digest CHAR(64) NOT NULL,
    canonical_internal_target VARCHAR(191) NOT NULL,
    target_version BIGINT UNSIGNED NOT NULL,
    source_alert_identity VARCHAR(191) NOT NULL,
    allowed_actor_ref VARCHAR(191) NOT NULL,
    required_capability VARCHAR(100) NOT NULL,
    status ENUM('issued','redeemed','expired','revoked') NOT NULL DEFAULT 'issued',
    issued_at_utc DATETIME(6) NOT NULL,
    expires_at_utc DATETIME(6) NOT NULL,
    redeemed_at_utc DATETIME(6) NULL,
    revoked_at_utc DATETIME(6) NULL,
    root_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_safe_review_link_id (link_id),
    UNIQUE KEY uq_line_safe_review_token_digest (token_digest),
    UNIQUE KEY uq_line_safe_review_idempotency (idempotency_key),
    INDEX idx_line_safe_review_status_expiry (status, expires_at_utc),
    INDEX idx_line_safe_review_alert (source_alert_identity, created_at_utc),
    CONSTRAINT chk_line_safe_review_link_digest CHECK (
        token_digest REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_line_safe_review_link_identity CHECK (
        CHAR_LENGTH(TRIM(link_id)) > 0
        AND CHAR_LENGTH(TRIM(canonical_internal_target)) > 0
        AND CHAR_LENGTH(TRIM(source_alert_identity)) > 0
        AND CHAR_LENGTH(TRIM(allowed_actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(required_capability)) > 0
    ),
    CONSTRAINT chk_line_safe_review_link_expiry CHECK (expires_at_utc > issued_at_utc),
    CONSTRAINT chk_line_safe_review_link_terminal_times CHECK (
        (status = 'issued' AND redeemed_at_utc IS NULL AND revoked_at_utc IS NULL)
        OR (status = 'redeemed' AND redeemed_at_utc IS NOT NULL AND revoked_at_utc IS NULL)
        OR (status = 'expired' AND redeemed_at_utc IS NULL AND revoked_at_utc IS NULL)
        OR (status = 'revoked' AND revoked_at_utc IS NOT NULL AND redeemed_at_utc IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_safe_review_link_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    link_id BIGINT UNSIGNED NOT NULL,
    event_type ENUM('issued','redeemed','expired','revoked') NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    resulting_status ENUM('issued','redeemed','expired','revoked') NOT NULL,
    target_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    event_payload JSON NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_line_safe_review_event_idempotency (idempotency_key),
    INDEX idx_line_safe_review_event_link (link_id, id),
    CONSTRAINT fk_line_safe_review_event_link FOREIGN KEY (link_id)
        REFERENCES line_safe_review_links(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_safe_review_event_payload CHECK (
        JSON_TYPE(event_payload) = 'OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_safe_review_link_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    link_id BIGINT UNSIGNED NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    outcome ENUM('issued','redeemed','expired','revoked','rejected') NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_line_safe_review_receipt_link FOREIGN KEY (link_id)
        REFERENCES line_safe_review_links(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_safe_review_receipt_digest CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_line_safe_review_receipt_result CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_safe_review_link_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    link_id BIGINT UNSIGNED NOT NULL,
    intent_type ENUM('safe_review_link_issued') NOT NULL,
    target_owner ENUM('line_integration') NOT NULL DEFAULT 'line_integration',
    intent_payload JSON NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_safe_review_outbox_idempotency (idempotency_key),
    INDEX idx_line_safe_review_outbox_link (link_id, id),
    CONSTRAINT fk_line_safe_review_outbox_link FOREIGN KEY (link_id)
        REFERENCES line_safe_review_links(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_safe_review_outbox_payload CHECK (
        JSON_TYPE(intent_payload) = 'OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_safe_review_links_before_delete;
CREATE TRIGGER trg_line_safe_review_links_before_delete
BEFORE DELETE ON line_safe_review_links FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_links records cannot be deleted';
DROP TRIGGER IF EXISTS trg_line_safe_review_link_events_before_update;
CREATE TRIGGER trg_line_safe_review_link_events_before_update
BEFORE UPDATE ON line_safe_review_link_events FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_events records cannot be updated';
DROP TRIGGER IF EXISTS trg_line_safe_review_link_events_before_delete;
CREATE TRIGGER trg_line_safe_review_link_events_before_delete
BEFORE DELETE ON line_safe_review_link_events FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_events records cannot be deleted';
DROP TRIGGER IF EXISTS trg_line_safe_review_link_receipts_before_update;
CREATE TRIGGER trg_line_safe_review_link_receipts_before_update
BEFORE UPDATE ON line_safe_review_link_receipts FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_receipts records cannot be updated';
DROP TRIGGER IF EXISTS trg_line_safe_review_link_receipts_before_delete;
CREATE TRIGGER trg_line_safe_review_link_receipts_before_delete
BEFORE DELETE ON line_safe_review_link_receipts FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_receipts records cannot be deleted';
DROP TRIGGER IF EXISTS trg_line_safe_review_link_outbox_before_update;
CREATE TRIGGER trg_line_safe_review_link_outbox_before_update
BEFORE UPDATE ON line_safe_review_link_outbox FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_outbox records cannot be updated';
DROP TRIGGER IF EXISTS trg_line_safe_review_link_outbox_before_delete;
CREATE TRIGGER trg_line_safe_review_link_outbox_before_delete
BEFORE DELETE ON line_safe_review_link_outbox FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_outbox records cannot be deleted';

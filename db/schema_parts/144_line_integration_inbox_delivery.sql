-- Canonical LINE webhook inbox, delivery queue, receipts, outbox, and audit facts.
-- Legacy LINE tables remain untouched until the runtime cutover stage.

CREATE TABLE IF NOT EXISTS line_inbox_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    provider_event_id VARCHAR(191) NULL,
    destination_id VARCHAR(191) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    source_type ENUM('user','group','room') NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_user_id VARCHAR(191) NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    identity_source ENUM('provider','fingerprint','legacy') NOT NULL,
    is_redelivery BOOLEAN NOT NULL DEFAULT FALSE,
    processing_status ENUM(
        'pending','processing','processed','retryable_failed','terminal_failed'
    ) NOT NULL DEFAULT 'pending',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_acquired_at_utc DATETIME(6) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    received_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    processed_at_utc DATETIME(6) NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_inbox_event_identity (event_identity),
    INDEX idx_line_inbox_due (
        processing_status, next_attempt_at_utc, received_at_utc, id
    ),
    INDEX idx_line_inbox_lease (processing_status, lease_expires_at_utc),
    CONSTRAINT chk_line_inbox_payload_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_inbox_payload_object
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_inbox_lease_pair CHECK (
        (lease_owner IS NULL AND lease_acquired_at_utc IS NULL AND lease_expires_at_utc IS NULL)
        OR
        (lease_owner IS NOT NULL AND lease_acquired_at_utc IS NOT NULL
            AND lease_expires_at_utc > lease_acquired_at_utc)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_inbox_events (
    id, event_identity, provider_event_id, destination_id, event_type,
    source_type, source_identity, source_user_id, occurred_at_utc,
    payload_fingerprint, payload_snapshot, identity_source, is_redelivery,
    processing_status, aggregate_version, error_message, received_at_utc,
    processed_at_utc
)
SELECT
    id,
    webhook_event_id,
    webhook_event_id,
    'legacy:unknown',
    event_type,
    CASE WHEN source_type IN ('group','room') THEN source_type ELSE 'user' END,
    COALESCE(source_group_id, source_user_id, 'legacy:unknown'),
    source_user_id,
    COALESCE(FROM_UNIXTIME(event_timestamp / 1000.0), received_at),
    SHA2(CAST(payload_json AS CHAR CHARACTER SET utf8mb4), 256),
    payload_json,
    'legacy',
    is_redelivery,
    CASE processing_status
        WHEN 'received' THEN 'pending'
        WHEN 'processing' THEN 'processing'
        WHEN 'completed' THEN 'processed'
        WHEN 'ignored' THEN 'processed'
        ELSE 'terminal_failed'
    END,
    0,
    error_message,
    received_at,
    processed_at
FROM line_webhook_events;

CREATE TABLE IF NOT EXISTS line_delivery_tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recipient_type ENUM('user','group','room') NOT NULL,
    recipient_identity VARCHAR(191) NOT NULL,
    message_kind ENUM('text','flex') NOT NULL,
    payload_snapshot JSON NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    scheduled_at_utc DATETIME(6) NOT NULL,
    source_aggregate_type VARCHAR(191) NOT NULL,
    source_aggregate_identity VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    processing_status ENUM(
        'pending','processing','sent','retryable_failed','failed','cancelled'
    ) NOT NULL DEFAULT 'pending',
    completed_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_acquired_at_utc DATETIME(6) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    provider_message_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    sent_at_utc DATETIME(6) NULL,
    failed_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_delivery_idempotency (idempotency_key),
    INDEX idx_line_delivery_due (
        processing_status, scheduled_at_utc, next_attempt_at_utc, id
    ),
    INDEX idx_line_delivery_lease (processing_status, lease_expires_at_utc),
    INDEX idx_line_delivery_source (
        source_aggregate_type, source_aggregate_identity, id
    ),
    CONSTRAINT chk_line_delivery_payload_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_delivery_payload_object
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_delivery_lease_pair CHECK (
        (lease_owner IS NULL AND lease_acquired_at_utc IS NULL AND lease_expires_at_utc IS NULL)
        OR
        (lease_owner IS NOT NULL AND lease_acquired_at_utc IS NOT NULL
            AND lease_expires_at_utc > lease_acquired_at_utc)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_delivery_tasks (
    id, recipient_type, recipient_identity, message_kind, payload_snapshot,
    payload_fingerprint, scheduled_at_utc, source_aggregate_type,
    source_aggregate_identity, idempotency_key, correlation_id,
    processing_status, completed_attempts, max_attempts, next_attempt_at_utc,
    provider_message_id, error_code, error_message, sent_at_utc,
    failed_at_utc, created_at_utc, updated_at_utc
)
SELECT
    id,
    'user',
    to_user_id,
    CASE
        WHEN payload_json IS NOT NULL
          AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.type')) = 'flex'
        THEN 'flex'
        ELSE 'text'
    END,
    CASE
        WHEN payload_json IS NOT NULL AND JSON_TYPE(payload_json) = 'OBJECT'
        THEN payload_json
        ELSE JSON_OBJECT('text', COALESCE(message_content, ''), 'type', 'text')
    END,
    SHA2(CONCAT_WS('|', to_user_id, task_type, COALESCE(message_content, ''),
        COALESCE(CAST(payload_json AS CHAR CHARACTER SET utf8mb4), ''), scheduled_at), 256),
    scheduled_at,
    'legacy_line_task',
    CAST(id AS CHAR),
    COALESCE(idempotency_key, CONCAT('legacy-line-task:', id)),
    CONCAT('legacy-line-task:', id),
    CASE status
        WHEN 'pending' THEN 'pending'
        WHEN 'processing' THEN 'processing'
        WHEN 'sent' THEN 'sent'
        WHEN 'cancelled' THEN 'cancelled'
        ELSE 'failed'
    END,
    retry_count,
    max_retries,
    next_retry_at,
    NULL,
    error_code,
    error_message,
    sent_at,
    failed_at,
    created_at,
    updated_at
FROM line_tasks;

CREATE TABLE IF NOT EXISTS line_delivery_attempt_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id BIGINT UNSIGNED NOT NULL,
    attempt_number INT UNSIGNED NOT NULL,
    outcome ENUM(
        'success','retryable_failure','terminal_failure','legacy_incomplete'
    ) NOT NULL,
    provider_outcome_type ENUM(
        'success','rate_limited','rejected','unavailable','timeout','legacy'
    ) NOT NULL,
    provider_message_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    retry_after_seconds INT UNSIGNED NULL,
    started_at_utc DATETIME(6) NOT NULL,
    completed_at_utc DATETIME(6) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_delivery_attempt_number (task_id, attempt_number),
    UNIQUE KEY uq_line_delivery_attempt_idempotency (idempotency_key),
    INDEX idx_line_delivery_attempt_time (outcome, completed_at_utc),
    CONSTRAINT fk_line_delivery_attempt_task
        FOREIGN KEY (task_id) REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_delivery_attempt_events (
    id, task_id, attempt_number, outcome, provider_outcome_type,
    error_code, error_message, started_at_utc, completed_at_utc,
    idempotency_key, correlation_id
)
SELECT
    id,
    task_id,
    attempt_no,
    CASE outcome
        WHEN 'sent' THEN 'success'
        WHEN 'retry_scheduled' THEN 'retryable_failure'
        WHEN 'failed' THEN 'terminal_failure'
        ELSE 'legacy_incomplete'
    END,
    CASE outcome WHEN 'sent' THEN 'success' ELSE 'legacy' END,
    error_code,
    error_message,
    started_at,
    COALESCE(finished_at, started_at),
    CONCAT('legacy-line-attempt:', id),
    CONCAT('legacy-line-attempt:', id)
FROM line_task_attempts;

CREATE TABLE IF NOT EXISTS line_command_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_family VARCHAR(100) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    result_reference VARCHAR(191) NOT NULL,
    result_snapshot JSON NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_command_receipt_key (idempotency_key),
    INDEX idx_line_command_receipt_family (command_family, created_at_utc),
    CONSTRAINT chk_line_command_receipt_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_command_receipt_snapshot
        CHECK (result_snapshot IS NULL OR JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_domain_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    intent_type VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    idempotency_identity VARCHAR(191) NOT NULL,
    processing_status ENUM('pending','processing','completed','dead')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    error_code VARCHAR(191) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_line_domain_outbox_identity (idempotency_identity),
    INDEX idx_line_domain_outbox_due (
        processing_status, next_attempt_at_utc, created_at_utc, id
    ),
    CONSTRAINT chk_line_domain_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_domain_audit_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    action VARCHAR(191) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    aggregate_type VARCHAR(191) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_line_domain_audit_aggregate (
        aggregate_type, aggregate_identity, occurred_at_utc, id
    ),
    INDEX idx_line_domain_audit_actor (actor_id, occurred_at_utc, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_delivery_attempt_events_before_update;
CREATE TRIGGER trg_line_delivery_attempt_events_before_update
BEFORE UPDATE ON line_delivery_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_delivery_attempt_events_before_delete;
CREATE TRIGGER trg_line_delivery_attempt_events_before_delete
BEFORE DELETE ON line_delivery_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_command_receipts_before_update;
CREATE TRIGGER trg_line_command_receipts_before_update
BEFORE UPDATE ON line_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_command_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_command_receipts_before_delete;
CREATE TRIGGER trg_line_command_receipts_before_delete
BEFORE DELETE ON line_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_command_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_domain_audit_events_before_update;
CREATE TRIGGER trg_line_domain_audit_events_before_update
BEFORE UPDATE ON line_domain_audit_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_domain_audit_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_domain_audit_events_before_delete;
CREATE TRIGGER trg_line_domain_audit_events_before_delete
BEFORE DELETE ON line_domain_audit_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_domain_audit_events records cannot be deleted';

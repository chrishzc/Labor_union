-- Additive Government Subsidy claim planning, submission, and approval owner.

CREATE TABLE IF NOT EXISTS government_subsidy_claim_submission_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_submission_key (idempotency_key),
    UNIQUE KEY uq_government_subsidy_submission_batch (batch_id),
    CONSTRAINT fk_government_subsidy_submission_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_submission_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_subsidy_submission_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_government_subsidy_submission_actor
        CHECK (CHAR_LENGTH(TRIM(actor)) > 0),
    CONSTRAINT chk_government_subsidy_submission_reason
        CHECK (CHAR_LENGTH(TRIM(reason)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_approval_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    approved_total_ntd BIGINT UNSIGNED NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    approved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_approval_key (idempotency_key),
    UNIQUE KEY uq_government_subsidy_approval_batch (batch_id),
    UNIQUE KEY uq_government_subsidy_approval_identity (id, batch_id),
    CONSTRAINT fk_government_subsidy_approval_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_approval_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_subsidy_approval_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_government_subsidy_approval_actor
        CHECK (CHAR_LENGTH(TRIM(actor)) > 0),
    CONSTRAINT chk_government_subsidy_approval_reason
        CHECK (CHAR_LENGTH(TRIM(reason)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_approval_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    approval_event_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    claim_item_id BIGINT NOT NULL,
    approved_amount_ntd BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_approval_item (
        approval_event_id,
        claim_item_id
    ),
    CONSTRAINT fk_government_subsidy_approval_item_event
        FOREIGN KEY (approval_event_id, batch_id)
        REFERENCES government_subsidy_claim_approval_events(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_approval_item_claim
        FOREIGN KEY (claim_item_id, batch_id)
        REFERENCES subsidy_claim_batch_items(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('plan', 'submit', 'approval') NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_claim_outbox_intent (intent_key),
    INDEX idx_government_subsidy_claim_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_government_subsidy_claim_outbox_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_claim_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_kind ENUM('plan', 'submit', 'approval') NOT NULL,
    batch_id BIGINT NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    item_count INT UNSIGNED NOT NULL,
    total_ntd BIGINT UNSIGNED NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_claim_receipt_key (idempotency_key),
    CONSTRAINT fk_government_subsidy_claim_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_claim_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_government_subsidy_claim_receipt_items
        CHECK (item_count > 0),
    CONSTRAINT chk_government_subsidy_claim_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_subsidy_submission_before_update;
CREATE TRIGGER trg_government_subsidy_submission_before_update
BEFORE UPDATE ON government_subsidy_claim_submission_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_submission_before_delete;
CREATE TRIGGER trg_government_subsidy_submission_before_delete
BEFORE DELETE ON government_subsidy_claim_submission_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_before_update;
CREATE TRIGGER trg_government_subsidy_approval_before_update
BEFORE UPDATE ON government_subsidy_claim_approval_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_before_delete;
CREATE TRIGGER trg_government_subsidy_approval_before_delete
BEFORE DELETE ON government_subsidy_claim_approval_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_item_before_update;
CREATE TRIGGER trg_government_subsidy_approval_item_before_update
BEFORE UPDATE ON government_subsidy_claim_approval_items
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_approval_item_before_delete;
CREATE TRIGGER trg_government_subsidy_approval_item_before_delete
BEFORE DELETE ON government_subsidy_claim_approval_items
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_claim_receipt_before_update;
CREATE TRIGGER trg_government_subsidy_claim_receipt_before_update
BEFORE UPDATE ON government_subsidy_claim_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_claim_receipt_before_delete;
CREATE TRIGGER trg_government_subsidy_claim_receipt_before_delete
BEFORE DELETE ON government_subsidy_claim_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be deleted';

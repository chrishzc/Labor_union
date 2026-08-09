-- Additive Government Subsidy owner, immutable audit, and Apply receipts.

CREATE TABLE IF NOT EXISTS government_subsidy_batch_accounts (
    batch_id BIGINT PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    requested_total_ntd BIGINT UNSIGNED NOT NULL,
    approved_total_ntd BIGINT UNSIGNED NOT NULL,
    net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_government_subsidy_account_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_account_version
        CHECK (aggregate_version > 0),
    CONSTRAINT chk_government_subsidy_account_totals
        CHECK (
            approved_total_ntd <= requested_total_ntd
            AND net_allocated_ntd <= approved_total_ntd
            AND outstanding_ntd = approved_total_ntd - net_allocated_ntd
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE government_subsidy_transactions
    ADD COLUMN expected_batch_version BIGINT UNSIGNED NULL
        AFTER reversal_target_type,
    ADD COLUMN resulting_batch_version BIGINT UNSIGNED NULL
        AFTER expected_batch_version,
    ADD COLUMN preview_fingerprint CHAR(64) NULL
        AFTER resulting_batch_version,
    ADD COLUMN idempotency_key VARCHAR(191) NULL
        AFTER preview_fingerprint,
    ADD COLUMN actor VARCHAR(100) NULL
        AFTER idempotency_key,
    ADD COLUMN reason VARCHAR(500) NULL
        AFTER actor,
    ADD COLUMN correlation_id VARCHAR(191) NULL
        AFTER reason,
    ADD UNIQUE KEY uq_government_subsidy_transaction_idempotency (
        idempotency_key
    ),
    ADD CONSTRAINT chk_government_subsidy_transaction_new_version
        CHECK (
            expected_batch_version IS NULL
            OR resulting_batch_version = expected_batch_version + 1
        ),
    ADD CONSTRAINT chk_government_subsidy_transaction_new_fingerprint
        CHECK (
            preview_fingerprint IS NULL
            OR preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        );

CREATE TABLE IF NOT EXISTS government_subsidy_projection_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL,
    before_status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    after_status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    before_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    after_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_projection_event_key (
        idempotency_key
    ),
    UNIQUE KEY uq_government_subsidy_projection_event_identity (
        id,
        batch_id
    ),
    CONSTRAINT fk_government_subsidy_projection_event_account
        FOREIGN KEY (batch_id)
        REFERENCES government_subsidy_batch_accounts(batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_projection_event_transaction
        FOREIGN KEY (transaction_id, batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_projection_event_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_subsidy_projection_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_kind ENUM('receipt', 'reversal') NOT NULL,
    transaction_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL,
    bank_fact_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT UNSIGNED NOT NULL,
    allocation_count INT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_receipt_key (idempotency_key),
    CONSTRAINT fk_government_subsidy_receipt_transaction
        FOREIGN KEY (transaction_id, batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_government_subsidy_receipt_amount
        CHECK (amount_ntd > 0 AND allocation_count > 0),
    CONSTRAINT chk_government_subsidy_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL,
    projection_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed'
    ) NOT NULL,
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
    UNIQUE KEY uq_government_subsidy_outbox_intent (intent_key),
    INDEX idx_government_subsidy_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_government_subsidy_outbox_transaction
        FOREIGN KEY (transaction_id, batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_outbox_projection
        FOREIGN KEY (projection_event_id, batch_id)
        REFERENCES government_subsidy_projection_events(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_subsidy_transactions_before_update;
CREATE TRIGGER trg_government_subsidy_transactions_before_update
BEFORE UPDATE ON government_subsidy_transactions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_transactions_before_delete;
CREATE TRIGGER trg_government_subsidy_transactions_before_delete
BEFORE DELETE ON government_subsidy_transactions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_allocations_before_update;
CREATE TRIGGER trg_government_subsidy_allocations_before_update
BEFORE UPDATE ON government_subsidy_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_allocations_before_delete;
CREATE TRIGGER trg_government_subsidy_allocations_before_delete
BEFORE DELETE ON government_subsidy_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_projection_events_before_update;
CREATE TRIGGER trg_government_subsidy_projection_events_before_update
BEFORE UPDATE ON government_subsidy_projection_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_projection_events_before_delete;
CREATE TRIGGER trg_government_subsidy_projection_events_before_delete
BEFORE DELETE ON government_subsidy_projection_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_subsidy_receipts_before_update;
CREATE TRIGGER trg_government_subsidy_receipts_before_update
BEFORE UPDATE ON government_subsidy_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_receipts_before_delete;
CREATE TRIGGER trg_government_subsidy_receipts_before_delete
BEFORE DELETE ON government_subsidy_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be deleted';

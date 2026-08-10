-- Finance Import Preview/Apply control state and immutable audit.

CREATE TABLE IF NOT EXISTS finance_import_batch_contracts (
    batch_id BIGINT PRIMARY KEY,
    batch_identity VARCHAR(191) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    classifier_version VARCHAR(191) NOT NULL,
    fingerprint_version VARCHAR(191) NOT NULL,
    batch_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_batch_contract_identity (batch_identity),
    CONSTRAINT fk_finance_import_batch_contract_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_batch_contract_digest
        CHECK (source_content_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_batch_contract_text
        CHECK (
            CHAR_LENGTH(TRIM(batch_identity)) > 0
            AND CHAR_LENGTH(TRIM(classifier_version)) > 0
            AND CHAR_LENGTH(TRIM(fingerprint_version)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_classification_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    classification_version BIGINT UNSIGNED NOT NULL,
    canonical_fact_version BIGINT UNSIGNED NOT NULL,
    classification_type ENUM(
        'client_receipt',
        'client_subsidy_return',
        'government_subsidy',
        'staff_payout',
        'non_business_review'
    ) NOT NULL,
    disposition ENUM(
        'create',
        'existing',
        'manual_review',
        'business_pending',
        'blocked'
    ) NOT NULL,
    decision_facts_fingerprint CHAR(64) NOT NULL,
    target_identities JSON NOT NULL,
    evidence JSON NOT NULL,
    available_actions JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_classification_version (
        finance_import_row_id,
        classification_version
    ),
    INDEX idx_finance_import_classification_batch (
        batch_id,
        finance_import_row_id,
        id
    ),
    CONSTRAINT fk_finance_import_classification_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_classification_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_classification_fingerprint
        CHECK (decision_facts_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_classification_json
        CHECK (
            JSON_TYPE(target_identities) = 'ARRAY'
            AND JSON_TYPE(evidence) = 'ARRAY'
            AND JSON_TYPE(available_actions) = 'ARRAY'
        ),
    CONSTRAINT chk_finance_import_classification_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_integrity_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NULL,
    issue_code VARCHAR(191) NOT NULL,
    active TINYINT(1) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_integrity_source (source_event_identity),
    INDEX idx_finance_import_integrity_current (
        batch_id,
        finance_import_row_id,
        issue_code,
        id
    ),
    CONSTRAINT fk_finance_import_integrity_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_integrity_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_integrity_active
        CHECK (active IN (0, 1)),
    CONSTRAINT chk_finance_import_integrity_snapshot
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT'),
    CONSTRAINT chk_finance_import_integrity_text
        CHECK (
            CHAR_LENGTH(TRIM(issue_code)) > 0
            AND CHAR_LENGTH(TRIM(source_event_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_dispatch_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    plan_fingerprint CHAR(64) NOT NULL,
    outcome ENUM(
        'reconciled',
        'existing',
        'pending',
        'rejected',
        'conflict'
    ) NOT NULL,
    result_reference VARCHAR(191) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_dispatch_plan_row (
        plan_fingerprint,
        finance_import_row_id
    ),
    INDEX idx_finance_import_dispatch_batch (batch_id, id),
    CONSTRAINT fk_finance_import_dispatch_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_dispatch_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_dispatch_fingerprint
        CHECK (plan_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_dispatch_reference
        CHECK (
            (
                outcome IN ('reconciled', 'existing')
                AND result_reference IS NOT NULL
                AND CHAR_LENGTH(TRIM(result_reference)) > 0
            )
            OR (
                outcome IN ('pending', 'rejected', 'conflict')
                AND result_reference IS NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_reconciliation_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    finance_import_row_id BIGINT NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    owning_domain ENUM('client_finance', 'staff_payables') NOT NULL,
    allocation_count INT UNSIGNED NOT NULL,
    amount_ntd BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_reconciliation_candidate (
        candidate_fingerprint
    ),
    CONSTRAINT fk_finance_import_reconciliation_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_reconciliation_fingerprint
        CHECK (candidate_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_import_reconciliation_values
        CHECK (allocation_count > 0 AND amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    batch_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_apply_receipt_key (idempotency_key),
    CONSTRAINT fk_finance_import_apply_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_apply_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_apply_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_correction_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_correction_receipt_key (idempotency_key),
    CONSTRAINT fk_finance_import_correction_receipt_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_correction_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_correction_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'dispatch_completed',
        'manual_correction_completed',
        'initial_classification_recorded'
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
    UNIQUE KEY uq_finance_import_outbox_intent (intent_key),
    INDEX idx_finance_import_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_finance_import_outbox_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_classification_before_update;
CREATE TRIGGER trg_finance_import_classification_before_update
BEFORE UPDATE ON finance_import_classification_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_classification_before_delete;
CREATE TRIGGER trg_finance_import_classification_before_delete
BEFORE DELETE ON finance_import_classification_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_integrity_before_update;
CREATE TRIGGER trg_finance_import_integrity_before_update
BEFORE UPDATE ON finance_import_integrity_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_integrity_before_delete;
CREATE TRIGGER trg_finance_import_integrity_before_delete
BEFORE DELETE ON finance_import_integrity_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_dispatch_before_update;
CREATE TRIGGER trg_finance_import_dispatch_before_update
BEFORE UPDATE ON finance_import_dispatch_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_dispatch_before_delete;
CREATE TRIGGER trg_finance_import_dispatch_before_delete
BEFORE DELETE ON finance_import_dispatch_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_reconciliation_before_update;
CREATE TRIGGER trg_finance_import_reconciliation_before_update
BEFORE UPDATE ON finance_import_reconciliation_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_reconciliation_before_delete;
CREATE TRIGGER trg_finance_import_reconciliation_before_delete
BEFORE DELETE ON finance_import_reconciliation_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_apply_receipt_before_update;
CREATE TRIGGER trg_finance_import_apply_receipt_before_update
BEFORE UPDATE ON finance_import_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_apply_receipt_before_delete;
CREATE TRIGGER trg_finance_import_apply_receipt_before_delete
BEFORE DELETE ON finance_import_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_import_correction_receipt_before_update;
CREATE TRIGGER trg_finance_import_correction_receipt_before_update
BEFORE UPDATE ON finance_import_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_correction_receipt_before_delete;
CREATE TRIGGER trg_finance_import_correction_receipt_before_delete
BEFORE DELETE ON finance_import_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be deleted';

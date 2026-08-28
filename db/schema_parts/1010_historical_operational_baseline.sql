-- File: 1010_historical_operational_baseline.sql
-- Description: 保存歷史訂單作業基準的不可變事件、receipt 與僅可更新投遞 metadata 的 outbox。

CREATE TABLE IF NOT EXISTS historical_order_operational_baseline_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    baseline_event_identity VARCHAR(191) NOT NULL,
    prior_baseline_event_id BIGINT UNSIGNED NULL,
    order_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    selected_step TINYINT UNSIGNED NOT NULL,
    expected_orders_version BIGINT UNSIGNED NOT NULL,
    resulting_orders_version BIGINT UNSIGNED NOT NULL,
    owner_binding_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    evidence_mode ENUM(
        'retained',
        'historical_evidence_unavailable_accepted'
    ) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(191) NOT NULL,
    document_kind VARCHAR(191) NULL,
    affected_steps JSON NULL,
    candidate_snapshot JSON NOT NULL,
    step_projection JSON NOT NULL,
    preview_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    command_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor VARCHAR(255) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_operational_baseline_event_identity (
        baseline_event_identity
    ),
    UNIQUE KEY uq_historical_operational_baseline_prior_event (
        prior_baseline_event_id
    ),
    INDEX idx_historical_operational_baseline_case (
        case_no,
        resulting_orders_version,
        id
    ),
    INDEX idx_historical_operational_baseline_source (
        source_event_identity,
        source_version
    ),
    CONSTRAINT fk_historical_operational_baseline_prior
        FOREIGN KEY (prior_baseline_event_id)
        REFERENCES historical_order_operational_baseline_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_operational_baseline_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_operational_baseline_source
        FOREIGN KEY (source_event_identity)
        REFERENCES historical_order_adoption_receipts(source_event_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_operational_baseline_step
        CHECK (selected_step BETWEEN 1 AND 11),
    CONSTRAINT chk_historical_operational_baseline_versions
        CHECK (resulting_orders_version = expected_orders_version),
    CONSTRAINT chk_historical_operational_baseline_fingerprints
        CHECK (
            owner_binding_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_historical_operational_baseline_evidence
        CHECK (
            (
                evidence_mode = 'retained'
                AND document_kind IS NULL
                AND affected_steps IS NULL
            )
            OR (
                evidence_mode = 'historical_evidence_unavailable_accepted'
                AND CHAR_LENGTH(TRIM(document_kind)) > 0
                AND JSON_TYPE(affected_steps) = 'ARRAY'
                AND JSON_LENGTH(affected_steps) > 0
            )
        ),
    CONSTRAINT chk_historical_operational_baseline_snapshots
        CHECK (
            JSON_TYPE(candidate_snapshot) = 'OBJECT'
            AND JSON_TYPE(step_projection) = 'ARRAY'
            AND JSON_LENGTH(step_projection) = selected_step
        ),
    CONSTRAINT chk_historical_operational_baseline_text
        CHECK (
            CHAR_LENGTH(TRIM(baseline_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
            AND CHAR_LENGTH(TRIM(source_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(evidence_reference)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_operational_baseline_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_identity VARCHAR(191) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    resulting_orders_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    actor VARCHAR(255) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_operational_baseline_receipt_identity (
        receipt_identity
    ),
    UNIQUE KEY uq_historical_operational_baseline_receipt_event (event_id),
    UNIQUE KEY uq_historical_operational_baseline_receipt_idempotency (
        idempotency_key
    ),
    CONSTRAINT fk_historical_operational_baseline_receipt_event
        FOREIGN KEY (event_id)
        REFERENCES historical_order_operational_baseline_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_operational_baseline_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_historical_operational_baseline_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT'),
    CONSTRAINT chk_historical_operational_baseline_receipt_text
        CHECK (
            CHAR_LENGTH(TRIM(receipt_identity)) > 0
            AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_operational_baseline_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id BIGINT UNSIGNED NOT NULL,
    receipt_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('historical_operational_baseline_confirmed') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_operational_baseline_outbox_event (event_id),
    UNIQUE KEY uq_historical_operational_baseline_outbox_receipt (receipt_id),
    UNIQUE KEY uq_historical_operational_baseline_outbox_intent (intent_key),
    INDEX idx_historical_operational_baseline_outbox_pending (
        published_at,
        attempts,
        id
    ),
    CONSTRAINT fk_historical_operational_baseline_outbox_event
        FOREIGN KEY (event_id)
        REFERENCES historical_order_operational_baseline_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_operational_baseline_outbox_receipt
        FOREIGN KEY (receipt_id)
        REFERENCES historical_order_operational_baseline_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_operational_baseline_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_historical_operational_baseline_outbox_text
        CHECK (CHAR_LENGTH(TRIM(intent_key)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_operational_baseline_events_before_update;
CREATE TRIGGER trg_historical_operational_baseline_events_before_update
BEFORE UPDATE ON historical_order_operational_baseline_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_operational_baseline_events_before_delete;
CREATE TRIGGER trg_historical_operational_baseline_events_before_delete
BEFORE DELETE ON historical_order_operational_baseline_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_operational_baseline_receipts_before_update;
CREATE TRIGGER trg_historical_operational_baseline_receipts_before_update
BEFORE UPDATE ON historical_order_operational_baseline_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_operational_baseline_receipts_before_delete;
CREATE TRIGGER trg_historical_operational_baseline_receipts_before_delete
BEFORE DELETE ON historical_order_operational_baseline_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_operational_baseline_outbox_before_update;
CREATE TRIGGER trg_historical_operational_baseline_outbox_before_update
BEFORE UPDATE ON historical_order_operational_baseline_outbox
FOR EACH ROW SET NEW.event_id = IF(
    OLD.id <=> NEW.id
    AND OLD.event_id <=> NEW.event_id
    AND OLD.receipt_id <=> NEW.receipt_id
    AND OLD.intent_key <=> NEW.intent_key
    AND OLD.intent_type <=> NEW.intent_type
    AND OLD.bounded_snapshot <=> NEW.bounded_snapshot
    AND OLD.created_at <=> NEW.created_at,
    NEW.event_id,
    NULL
);

DROP TRIGGER IF EXISTS trg_historical_operational_baseline_outbox_before_delete;
CREATE TRIGGER trg_historical_operational_baseline_outbox_before_delete
BEFORE DELETE ON historical_order_operational_baseline_outbox
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_outbox records cannot be deleted';

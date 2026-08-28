-- File: 1006_historical_order_review_remediation.sql
-- Description: 保存 Historical Order review 的不可變人工更正 disposition、receipt 與 outbox。

CREATE TABLE IF NOT EXISTS historical_order_review_remediation_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_identity VARCHAR(191) NOT NULL,
    prior_review_identity VARCHAR(191) NOT NULL,
    original_adoption_receipt_id BIGINT UNSIGNED NOT NULL,
    replacement_adoption_receipt_id BIGINT UNSIGNED NOT NULL,
    disposition ENUM('corrected_source_adopted','superseded_by_replacement_review') NOT NULL,
    successor_review_identity VARCHAR(191) NULL,
    source_content_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    review_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor VARCHAR(255) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    applied_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_review_remediation_event (event_identity),
    UNIQUE KEY uq_historical_order_review_remediation_prior (prior_review_identity),
    UNIQUE KEY uq_historical_order_review_remediation_replacement (replacement_adoption_receipt_id),
    INDEX idx_historical_order_review_remediation_successor (successor_review_identity, id),
    CONSTRAINT fk_historical_order_review_remediation_prior
        FOREIGN KEY (prior_review_identity) REFERENCES historical_order_adoption_reviews(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_review_remediation_original_receipt
        FOREIGN KEY (original_adoption_receipt_id) REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_review_remediation_replacement_receipt
        FOREIGN KEY (replacement_adoption_receipt_id) REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_review_remediation_successor
        FOREIGN KEY (successor_review_identity) REFERENCES historical_order_adoption_reviews(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_review_remediation_fingerprints
        CHECK (
            source_content_digest REGEXP '^[0-9a-f]{64}$'
            AND review_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_historical_order_review_remediation_evidence
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT'),
    CONSTRAINT chk_historical_order_review_remediation_disposition
        CHECK (
            (disposition = 'corrected_source_adopted' AND successor_review_identity IS NULL)
            OR (disposition = 'superseded_by_replacement_review' AND successor_review_identity IS NOT NULL)
        ),
    CONSTRAINT chk_historical_order_review_remediation_replacement
        CHECK (replacement_adoption_receipt_id <> original_adoption_receipt_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_review_remediation_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    remediation_receipt_identity VARCHAR(191) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    expected_remediation_version BIGINT UNSIGNED NOT NULL,
    resulting_remediation_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    actor VARCHAR(255) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_review_remediation_receipt (remediation_receipt_identity),
    UNIQUE KEY uq_historical_order_review_remediation_receipt_event (event_id),
    UNIQUE KEY uq_historical_order_review_remediation_receipt_idempotency (idempotency_key),
    CONSTRAINT fk_historical_order_review_remediation_receipt_event
        FOREIGN KEY (event_id) REFERENCES historical_order_review_remediation_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_review_remediation_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_historical_order_review_remediation_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT'),
    CONSTRAINT chk_historical_order_review_remediation_receipt_version
        CHECK (expected_remediation_version = 0 AND resulting_remediation_version = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_review_remediation_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id BIGINT UNSIGNED NOT NULL,
    remediation_receipt_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('historical_order_review_remediated') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_review_remediation_outbox_intent (intent_key),
    INDEX idx_historical_order_review_remediation_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_historical_order_review_remediation_outbox_event
        FOREIGN KEY (event_id) REFERENCES historical_order_review_remediation_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_review_remediation_outbox_receipt
        FOREIGN KEY (remediation_receipt_id) REFERENCES historical_order_review_remediation_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_review_remediation_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_order_review_remediation_events_before_update;
CREATE TRIGGER trg_historical_order_review_remediation_events_before_update
BEFORE UPDATE ON historical_order_review_remediation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_review_remediation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_review_remediation_events_before_delete;
CREATE TRIGGER trg_historical_order_review_remediation_events_before_delete
BEFORE DELETE ON historical_order_review_remediation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_review_remediation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_order_review_remediation_receipts_before_update;
CREATE TRIGGER trg_historical_order_review_remediation_receipts_before_update
BEFORE UPDATE ON historical_order_review_remediation_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_review_remediation_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_review_remediation_receipts_before_delete;
CREATE TRIGGER trg_historical_order_review_remediation_receipts_before_delete
BEFORE DELETE ON historical_order_review_remediation_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_review_remediation_receipts records cannot be deleted';

-- File: 190_historical_order_adoption.sql
-- Description: 新增 Historical Order Adoption receipt、pairing evidence、review 與 outbox。

CREATE TABLE IF NOT EXISTS historical_order_adoption_reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    review_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    masked_case_identity VARCHAR(64) NOT NULL,
    issue_codes JSON NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_review_identity (review_identity),
    UNIQUE KEY uq_historical_order_review_source (source_event_identity),
    CONSTRAINT chk_historical_order_review_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_historical_order_review_payloads
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_adoption_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    case_no VARCHAR(50) NULL,
    outcome ENUM('adopted','review_required','current_conflict','unmatched_case') NOT NULL,
    expected_version BIGINT UNSIGNED NULL,
    resulting_version BIGINT UNSIGNED NULL,
    lifecycle_event_id BIGINT UNSIGNED NULL,
    assignment_count INT UNSIGNED NOT NULL DEFAULT 0,
    review_identity VARCHAR(191) NULL,
    result_snapshot JSON NOT NULL,
    actor VARCHAR(255) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_adoption_key (idempotency_key),
    UNIQUE KEY uq_historical_order_adoption_source (source_event_identity),
    INDEX idx_historical_order_adoption_case (case_no, created_at),
    CONSTRAINT fk_historical_order_adoption_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_adoption_lifecycle_event
        FOREIGN KEY (lifecycle_event_id) REFERENCES order_lifecycle_state_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_adoption_review
        FOREIGN KEY (review_identity) REFERENCES historical_order_adoption_reviews(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_adoption_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_historical_order_adoption_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT'),
    CONSTRAINT chk_historical_order_adoption_shape
        CHECK (
            (outcome = 'unmatched_case' AND lifecycle_event_id IS NULL
             AND expected_version IS NULL AND resulting_version IS NULL)
            OR
            (outcome = 'adopted' AND lifecycle_event_id IS NOT NULL
             AND expected_version IS NOT NULL AND resulting_version = expected_version + 1
             AND case_no IS NOT NULL)
            OR
            (outcome IN ('review_required','current_conflict') AND lifecycle_event_id IS NULL
             AND expected_version IS NOT NULL AND resulting_version = expected_version
             AND case_no IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_pairing_evidence (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_id BIGINT UNSIGNED NOT NULL,
    caregiver_ordinal INT UNSIGNED NOT NULL,
    masked_staff_name VARCHAR(100) NOT NULL,
    staff_id INT NULL,
    resolution ENUM(
        'blank','staff_missing','staff_ambiguous','evidence_only',
        'assignment_candidate','assignment_conflict'
    ) NOT NULL,
    source_start_date DATE NULL,
    source_end_date DATE NULL,
    assignment_id BIGINT NULL,
    issue_codes JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_pairing_ordinal (receipt_id, caregiver_ordinal),
    INDEX idx_historical_order_pairing_staff (staff_id, created_at),
    CONSTRAINT fk_historical_order_pairing_receipt
        FOREIGN KEY (receipt_id) REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_pairing_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_order_pairing_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_pairing_ordinal CHECK (caregiver_ordinal > 0),
    CONSTRAINT chk_historical_order_pairing_issues CHECK (JSON_TYPE(issue_codes) = 'ARRAY'),
    CONSTRAINT chk_historical_order_pairing_assignment_shape
        CHECK (
            (resolution = 'assignment_candidate' AND assignment_id IS NOT NULL AND staff_id IS NOT NULL)
            OR (resolution <> 'assignment_candidate' AND assignment_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_order_adoption_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('historical_order_adopted','historical_order_review_required') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_historical_order_adoption_outbox_intent (intent_key),
    INDEX idx_historical_order_adoption_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_historical_order_adoption_outbox_receipt
        FOREIGN KEY (receipt_id) REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_order_adoption_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_order_adoption_reviews_before_update;
CREATE TRIGGER trg_historical_order_adoption_reviews_before_update
BEFORE UPDATE ON historical_order_adoption_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_reviews records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_adoption_reviews_before_delete;
CREATE TRIGGER trg_historical_order_adoption_reviews_before_delete
BEFORE DELETE ON historical_order_adoption_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_reviews records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_order_adoption_receipts_before_update;
CREATE TRIGGER trg_historical_order_adoption_receipts_before_update
BEFORE UPDATE ON historical_order_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_adoption_receipts_before_delete;
CREATE TRIGGER trg_historical_order_adoption_receipts_before_delete
BEFORE DELETE ON historical_order_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_order_pairing_evidence_before_update;
CREATE TRIGGER trg_historical_order_pairing_evidence_before_update
BEFORE UPDATE ON historical_order_pairing_evidence
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_pairing_evidence records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_order_pairing_evidence_before_delete;
CREATE TRIGGER trg_historical_order_pairing_evidence_before_delete
BEFORE DELETE ON historical_order_pairing_evidence
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_pairing_evidence records cannot be deleted';

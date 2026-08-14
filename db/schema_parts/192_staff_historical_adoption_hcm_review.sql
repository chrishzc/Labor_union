-- File: 192_staff_historical_adoption_hcm_review.sql
-- Description: 新增 Staff 歷史採納 receipt 與 HCM Case Import review/outbox。

CREATE TABLE IF NOT EXISTS staff_historical_adoption_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    staff_id INT NULL,
    outcome ENUM(
        'created', 'adopted_existing', 'blocked_identity',
        'identity_conflict', 'failed_retryable'
    ) NOT NULL,
    changed_fields JSON NOT NULL,
    review_identity VARCHAR(191) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_historical_adoption_key (idempotency_key),
    UNIQUE KEY uq_staff_historical_adoption_source (source_event_identity),
    CONSTRAINT fk_staff_historical_adoption_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_historical_adoption_review
        FOREIGN KEY (review_identity) REFERENCES beclass_import_review_rows(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_historical_adoption_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_staff_historical_adoption_changed_fields
        CHECK (JSON_TYPE(changed_fields) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_review_rows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_content_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_sheet_identity CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row INT NOT NULL,
    masked_case_identity VARCHAR(64) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    issue_codes JSON NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_hcm_review_identity (review_identity),
    UNIQUE KEY uq_case_import_hcm_review_source (source_event_identity),
    CONSTRAINT chk_case_import_hcm_review_digests
        CHECK (
            source_content_digest REGEXP '^[0-9a-f]{64}$'
            AND source_sheet_identity REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_import_hcm_review_source_row CHECK (source_row > 0),
    CONSTRAINT chk_case_import_hcm_review_payloads
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_review_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_row_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_hcm_review_outbox_intent (intent_key),
    INDEX idx_case_import_hcm_review_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_case_import_hcm_review_outbox_row
        FOREIGN KEY (review_row_id) REFERENCES case_import_hcm_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_import_hcm_review_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_case_import_hcm_review_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_historical_adoption_receipts_before_update;
CREATE TRIGGER trg_staff_historical_adoption_receipts_before_update
BEFORE UPDATE ON staff_historical_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_historical_adoption_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_historical_adoption_receipts_before_delete;
CREATE TRIGGER trg_staff_historical_adoption_receipts_before_delete
BEFORE DELETE ON staff_historical_adoption_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_historical_adoption_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_import_hcm_review_rows_before_update;
CREATE TRIGGER trg_case_import_hcm_review_rows_before_update
BEFORE UPDATE ON case_import_hcm_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_rows records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_import_hcm_review_rows_before_delete;
CREATE TRIGGER trg_case_import_hcm_review_rows_before_delete
BEFORE DELETE ON case_import_hcm_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_rows records cannot be deleted';

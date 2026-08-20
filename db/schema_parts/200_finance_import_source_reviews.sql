-- File: 200_finance_import_source_reviews.sql
-- Description: 新增 Finance 去敏來源列 review、批次 occurrence 與投影 outbox。

CREATE TABLE IF NOT EXISTS finance_import_source_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_identity VARCHAR(191) NOT NULL,
    source_content_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    format_id ENUM('legacy', 'taishin', 'sinopac') NOT NULL,
    sheet_name VARCHAR(191) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    masked_source_identity VARCHAR(191) NOT NULL,
    issue_codes JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_source_review_identity (review_identity),
    UNIQUE KEY uq_finance_source_review_source (
        source_content_digest, format_id, sheet_name, source_row
    ),
    INDEX idx_finance_source_review_location (format_id, sheet_name, source_row),
    CONSTRAINT chk_finance_source_review_digest
        CHECK (source_content_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_source_review_row CHECK (source_row >= 1),
    CONSTRAINT chk_finance_source_review_issues
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_LENGTH(issue_codes) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_source_review_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    review_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_source_review_occurrence (batch_id, review_id),
    INDEX idx_finance_source_review_occurrence_review (review_id, id),
    CONSTRAINT fk_finance_source_review_occurrence_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_source_review_occurrence_review
        FOREIGN KEY (review_id) REFERENCES finance_import_source_reviews(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_source_review_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_source_review_outbox_review (review_id),
    UNIQUE KEY uq_finance_source_review_outbox_intent (intent_key),
    INDEX idx_finance_source_review_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_finance_source_review_outbox_review
        FOREIGN KEY (review_id) REFERENCES finance_import_source_reviews(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_source_review_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_source_reviews_before_update;
CREATE TRIGGER trg_finance_import_source_reviews_before_update
BEFORE UPDATE ON finance_import_source_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_reviews cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_source_reviews_before_delete;
CREATE TRIGGER trg_finance_import_source_reviews_before_delete
BEFORE DELETE ON finance_import_source_reviews
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_reviews cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_source_review_occurrences_before_update;
CREATE TRIGGER trg_finance_source_review_occurrences_before_update
BEFORE UPDATE ON finance_import_source_review_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_review_occurrences cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_source_review_occurrences_before_delete;
CREATE TRIGGER trg_finance_source_review_occurrences_before_delete
BEFORE DELETE ON finance_import_source_review_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_review_occurrences cannot be deleted';

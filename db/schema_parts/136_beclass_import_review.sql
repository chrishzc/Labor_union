-- Append-only invalid-row evidence and correction workflow for BeClass imports.

CREATE TABLE IF NOT EXISTS beclass_import_review_rows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_identity VARCHAR(191) NOT NULL,
    source_kind ENUM('client', 'staff') NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_sheet VARCHAR(191) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    masked_identifier VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    source_payload JSON NOT NULL,
    issue_codes JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_identity (review_identity),
    UNIQUE KEY uq_beclass_review_source_event (
        source_kind,
        source_event_identity
    ),
    CONSTRAINT chk_beclass_review_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_beclass_review_payload
        CHECK (JSON_TYPE(source_payload) = 'OBJECT'),
    CONSTRAINT chk_beclass_review_issues
        CHECK (
            JSON_TYPE(issue_codes) = 'ARRAY'
            AND JSON_LENGTH(issue_codes) > 0
        ),
    CONSTRAINT chk_beclass_review_source_location
        CHECK (
            CHAR_LENGTH(TRIM(source_sheet)) > 0
            AND source_row > 0
            AND CHAR_LENGTH(TRIM(masked_identifier)) > 0
            AND LOCATE('*', masked_identifier) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_import_review_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_row_id BIGINT NOT NULL,
    event_type ENUM('resolved') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    owning_record_identity VARCHAR(191) NOT NULL,
    corrected_payload JSON NOT NULL,
    resolved_issue_codes JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_event_version (
        review_row_id,
        resulting_version
    ),
    UNIQUE KEY uq_beclass_review_event_idempotency (idempotency_key),
    CONSTRAINT fk_beclass_review_event_row
        FOREIGN KEY (review_row_id) REFERENCES beclass_import_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_review_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_beclass_review_event_fingerprint
        CHECK (candidate_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_beclass_review_event_payload
        CHECK (JSON_TYPE(corrected_payload) = 'OBJECT'),
    CONSTRAINT chk_beclass_review_event_issues
        CHECK (JSON_TYPE(resolved_issue_codes) = 'ARRAY'),
    CONSTRAINT chk_beclass_review_event_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_import_review_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_row_id BIGINT NOT NULL,
    review_event_id BIGINT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('review_opened', 'review_resolved') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at DATETIME NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_outbox_intent (intent_key),
    INDEX idx_beclass_review_outbox_pending (published_at, id),
    CONSTRAINT fk_beclass_review_outbox_row
        FOREIGN KEY (review_row_id) REFERENCES beclass_import_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_beclass_review_outbox_event
        FOREIGN KEY (review_event_id) REFERENCES beclass_import_review_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_review_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_beclass_review_outbox_event_shape
        CHECK (
            (intent_type = 'review_opened' AND review_event_id IS NULL)
            OR (intent_type = 'review_resolved' AND review_event_id IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_import_review_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    review_row_id BIGINT NOT NULL,
    owning_record_identity VARCHAR(191) NOT NULL,
    review_event_id BIGINT NOT NULL,
    outbox_id BIGINT NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_beclass_review_receipt_key (idempotency_key),
    UNIQUE KEY uq_beclass_review_receipt_event (review_event_id),
    CONSTRAINT fk_beclass_review_receipt_row
        FOREIGN KEY (review_row_id) REFERENCES beclass_import_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_beclass_review_receipt_event
        FOREIGN KEY (review_event_id) REFERENCES beclass_import_review_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_beclass_review_receipt_outbox
        FOREIGN KEY (outbox_id) REFERENCES beclass_import_review_outbox(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_review_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_beclass_review_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_beclass_review_rows_before_update;
CREATE TRIGGER trg_beclass_review_rows_before_update
BEFORE UPDATE ON beclass_import_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be updated';

DROP TRIGGER IF EXISTS trg_beclass_review_rows_before_delete;
CREATE TRIGGER trg_beclass_review_rows_before_delete
BEFORE DELETE ON beclass_import_review_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be deleted';

DROP TRIGGER IF EXISTS trg_beclass_review_events_before_update;
CREATE TRIGGER trg_beclass_review_events_before_update
BEFORE UPDATE ON beclass_import_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_beclass_review_events_before_delete;
CREATE TRIGGER trg_beclass_review_events_before_delete
BEFORE DELETE ON beclass_import_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_beclass_review_receipts_before_update;
CREATE TRIGGER trg_beclass_review_receipts_before_update
BEFORE UPDATE ON beclass_import_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_beclass_review_receipts_before_delete;
CREATE TRIGGER trg_beclass_review_receipts_before_delete
BEFORE DELETE ON beclass_import_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be deleted';

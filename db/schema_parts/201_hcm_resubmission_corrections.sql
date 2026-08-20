-- File: 201_hcm_resubmission_corrections.sql
-- Description: 新增 HCM 修正版來源的案件綁定、採納事件、receipt 與重掃 outbox。

CREATE TABLE IF NOT EXISTS case_import_hcm_review_case_bindings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    binding_identity VARCHAR(191) NOT NULL,
    review_row_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    root_import_event_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_review_case_binding_identity (binding_identity),
    UNIQUE KEY uq_hcm_review_case_binding_review (review_row_id),
    INDEX idx_hcm_review_case_binding_case (case_no, id),
    CONSTRAINT fk_hcm_review_case_binding_review
        FOREIGN KEY (review_row_id) REFERENCES case_import_hcm_review_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_review_case_binding_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_review_case_binding_import_event
        FOREIGN KEY (root_import_event_id) REFERENCES case_import_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_correction_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    review_binding_id BIGINT NOT NULL,
    prior_occurrence_id BIGINT NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    candidate_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    adopted_field_paths JSON NOT NULL,
    root_before_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    root_after_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_correction_event_identity (event_identity),
    UNIQUE KEY uq_hcm_correction_event_prior_source (prior_occurrence_id, source_event_identity),
    INDEX idx_hcm_correction_event_case (case_no, id),
    INDEX idx_hcm_correction_event_prior (prior_occurrence_id, id),
    CONSTRAINT fk_hcm_correction_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_correction_event_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_correction_event_binding
        FOREIGN KEY (review_binding_id) REFERENCES case_import_hcm_review_case_bindings(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hcm_correction_event_occurrence
        FOREIGN KEY (prior_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hcm_correction_event_fingerprints
        CHECK (
            source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND candidate_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND root_before_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND root_after_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hcm_correction_event_fields
        CHECK (JSON_TYPE(adopted_field_paths) = 'ARRAY' AND JSON_LENGTH(adopted_field_paths) > 0),
    CONSTRAINT chk_hcm_correction_event_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_correction_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    correction_event_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_correction_receipt_key (idempotency_key),
    UNIQUE KEY uq_hcm_correction_receipt_event (correction_event_id),
    CONSTRAINT fk_hcm_correction_receipt_event
        FOREIGN KEY (correction_event_id) REFERENCES case_import_hcm_correction_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hcm_correction_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hcm_correction_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_hcm_correction_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    correction_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_hcm_correction_outbox_event (correction_event_id),
    UNIQUE KEY uq_hcm_correction_outbox_intent (intent_key),
    INDEX idx_hcm_correction_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_hcm_correction_outbox_event
        FOREIGN KEY (correction_event_id) REFERENCES case_import_hcm_correction_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hcm_correction_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_hcm_correction_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_hcm_review_case_bindings_before_update;
CREATE TRIGGER trg_hcm_review_case_bindings_before_update
BEFORE UPDATE ON case_import_hcm_review_case_bindings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_case_bindings cannot be updated';

DROP TRIGGER IF EXISTS trg_hcm_review_case_bindings_before_delete;
CREATE TRIGGER trg_hcm_review_case_bindings_before_delete
BEFORE DELETE ON case_import_hcm_review_case_bindings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_case_bindings cannot be deleted';

DROP TRIGGER IF EXISTS trg_hcm_correction_events_before_update;
CREATE TRIGGER trg_hcm_correction_events_before_update
BEFORE UPDATE ON case_import_hcm_correction_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_events cannot be updated';

DROP TRIGGER IF EXISTS trg_hcm_correction_events_before_delete;
CREATE TRIGGER trg_hcm_correction_events_before_delete
BEFORE DELETE ON case_import_hcm_correction_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_events cannot be deleted';

DROP TRIGGER IF EXISTS trg_hcm_correction_receipts_before_update;
CREATE TRIGGER trg_hcm_correction_receipts_before_update
BEFORE UPDATE ON case_import_hcm_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_hcm_correction_receipts_before_delete;
CREATE TRIGGER trg_hcm_correction_receipts_before_delete
BEFORE DELETE ON case_import_hcm_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_receipts cannot be deleted';

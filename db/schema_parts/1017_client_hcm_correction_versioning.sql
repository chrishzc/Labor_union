-- File: 1017_client_hcm_correction_versioning.sql
-- Description: Client-owned version/event/receipt evidence for HCM corrections.
-- Additive only. No data backfill, seed, drop, or Orders service_type column.

ALTER TABLE clients
    ADD COLUMN client_hcm_correction_version BIGINT UNSIGNED NOT NULL DEFAULT 0
    COMMENT 'Client-owned HCM correction aggregate version';

CREATE TABLE IF NOT EXISTS client_hcm_correction_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    client_id INT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    review_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    field_path VARCHAR(191) NOT NULL,
    source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    expected_client_version BIGINT UNSIGNED NOT NULL,
    resulting_client_version BIGINT UNSIGNED NOT NULL,
    before_values JSON NOT NULL,
    after_values JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_hcm_correction_event_identity (event_identity),
    INDEX idx_client_hcm_correction_event_client (client_id, id),
    INDEX idx_client_hcm_correction_event_review (review_identity, id),
    CONSTRAINT fk_client_hcm_correction_event_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_hcm_correction_event_case
        FOREIGN KEY (case_no) REFERENCES clients(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_hcm_correction_event_versions
        CHECK (resulting_client_version = expected_client_version + 1),
    CONSTRAINT chk_client_hcm_correction_event_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_client_hcm_correction_event_json
        CHECK (JSON_TYPE(before_values) = 'OBJECT' AND JSON_TYPE(after_values) = 'OBJECT'),
    CONSTRAINT chk_client_hcm_correction_event_text
        CHECK (
            CHAR_LENGTH(TRIM(event_identity)) > 0
            AND CHAR_LENGTH(TRIM(review_identity)) > 0
            AND CHAR_LENGTH(TRIM(source_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(field_path)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_hcm_correction_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    correction_event_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_hcm_correction_receipt_key (idempotency_key),
    UNIQUE KEY uq_client_hcm_correction_receipt_event (correction_event_id),
    CONSTRAINT fk_client_hcm_correction_receipt_event
        FOREIGN KEY (correction_event_id) REFERENCES client_hcm_correction_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_hcm_correction_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_client_hcm_correction_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_hcm_correction_events_before_update;
CREATE TRIGGER trg_client_hcm_correction_events_before_update
BEFORE UPDATE ON client_hcm_correction_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client HCM correction events cannot be updated';

DROP TRIGGER IF EXISTS trg_client_hcm_correction_events_before_delete;
CREATE TRIGGER trg_client_hcm_correction_events_before_delete
BEFORE DELETE ON client_hcm_correction_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client HCM correction events cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_hcm_correction_receipts_before_update;
CREATE TRIGGER trg_client_hcm_correction_receipts_before_update
BEFORE UPDATE ON client_hcm_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client HCM correction receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_hcm_correction_receipts_before_delete;
CREATE TRIGGER trg_client_hcm_correction_receipts_before_delete
BEFORE DELETE ON client_hcm_correction_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client HCM correction receipts cannot be deleted';

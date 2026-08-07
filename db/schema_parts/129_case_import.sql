-- Immutable evidence and replay receipts for atomic negotiated-case import.

CREATE TABLE IF NOT EXISTS case_import_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    bootstrap_event_id BIGINT NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    source_snapshot JSON NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_case (case_no),
    UNIQUE KEY uq_case_import_idempotency (idempotency_key),
    UNIQUE KEY uq_case_import_source (source_fingerprint),
    CONSTRAINT fk_case_import_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_bootstrap
        FOREIGN KEY (bootstrap_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_import_fingerprints
        CHECK (
            source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND candidate_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_import_snapshot
        CHECK (JSON_TYPE(source_snapshot) = 'OBJECT'),
    CONSTRAINT chk_case_import_text
        CHECK (
            CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    import_event_id BIGINT NOT NULL,
    bootstrap_event_id BIGINT NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_import_receipt_key (idempotency_key),
    UNIQUE KEY uq_case_import_receipt_event (import_event_id),
    CONSTRAINT fk_case_import_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_receipt_client
        FOREIGN KEY (client_id) REFERENCES clients(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_receipt_import_event
        FOREIGN KEY (import_event_id) REFERENCES case_import_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_import_receipt_bootstrap_event
        FOREIGN KEY (bootstrap_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_import_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_import_receipt_versions
        CHECK (
            order_version = 0
            AND client_finance_version = 0
            AND payroll_version = 0
            AND scheduling_version = 0
            AND scheduling_generation = 0
        ),
    CONSTRAINT chk_case_import_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_case_import_events_before_update;
CREATE TRIGGER trg_case_import_events_before_update
BEFORE UPDATE ON case_import_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_import_events_before_delete;
CREATE TRIGGER trg_case_import_events_before_delete
BEFORE DELETE ON case_import_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_import_receipts_before_update;
CREATE TRIGGER trg_case_import_receipts_before_update
BEFORE UPDATE ON case_import_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_import_receipts_before_delete;
CREATE TRIGGER trg_case_import_receipts_before_delete
BEFORE DELETE ON case_import_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be deleted';

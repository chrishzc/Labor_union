-- Immutable operator-confirmed review facts for an ambiguous returned client refund.
-- Recognition is intentionally not inferred from bank memo, name, account, or amount.

ALTER TABLE finance_import_outbox
    MODIFY COLUMN intent_type ENUM(
        'dispatch_completed',
        'manual_correction_completed',
        'initial_classification_recorded',
        'historical_reprocess_completed',
        'refund_return_review_recorded'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_refund_return_review_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    finance_import_row_id BIGINT NOT NULL,
    original_refund_ledger_entry_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_return_review_bank_refund (
        finance_import_row_id,
        original_refund_ledger_entry_id
    ),
    UNIQUE KEY uq_client_refund_return_review_idempotency (idempotency_key),
    INDEX idx_client_refund_return_review_case (case_no, created_at, id),
    CONSTRAINT fk_client_refund_return_review_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_return_review_ledger
        FOREIGN KEY (original_refund_ledger_entry_id)
        REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_return_review_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_return_review_evidence
        CHECK (JSON_TYPE(evidence) = 'ARRAY'),
    CONSTRAINT chk_client_refund_return_review_text
        CHECK (
            CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_refund_return_review_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    review_event_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_return_review_receipt_key (idempotency_key),
    UNIQUE KEY uq_client_refund_return_review_receipt_event (review_event_id),
    CONSTRAINT fk_client_refund_return_review_receipt_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_return_review_receipt_event
        FOREIGN KEY (review_event_id) REFERENCES client_refund_return_review_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_return_review_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_client_refund_return_review_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_return_review_event_before_update;
CREATE TRIGGER trg_client_refund_return_review_event_before_update
BEFORE UPDATE ON client_refund_return_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review events cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_return_review_event_before_delete;
CREATE TRIGGER trg_client_refund_return_review_event_before_delete
BEFORE DELETE ON client_refund_return_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review events cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_refund_return_review_receipt_before_update;
CREATE TRIGGER trg_client_refund_return_review_receipt_before_update
BEFORE UPDATE ON client_refund_return_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_return_review_receipt_before_delete;
CREATE TRIGGER trg_client_refund_return_review_receipt_before_delete
BEFORE DELETE ON client_refund_return_review_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review receipts cannot be deleted';

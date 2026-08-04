-- Additive contracts for typed historical Finance Import reprocess Apply.

ALTER TABLE finance_import_classification_events
    MODIFY COLUMN classification_type ENUM(
        'client_receipt',
        'client_refund',
        'client_subsidy_return',
        'government_subsidy',
        'staff_payout',
        'non_business_review'
    ) NOT NULL;

ALTER TABLE finance_import_outbox
    MODIFY COLUMN intent_type ENUM(
        'dispatch_completed',
        'manual_correction_completed',
        'initial_classification_recorded',
        'historical_reprocess_completed'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS finance_import_historical_reprocess_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    batch_id BIGINT NOT NULL,
    reprocess_run_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_historical_reprocess_receipt_key (idempotency_key),
    UNIQUE KEY uq_finance_import_historical_reprocess_receipt_run (reprocess_run_id),
    CONSTRAINT fk_finance_import_historical_reprocess_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_historical_reprocess_receipt_run
        FOREIGN KEY (reprocess_run_id) REFERENCES finance_import_reprocess_runs(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_historical_reprocess_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_historical_reprocess_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_historical_reprocess_receipt_before_update;
CREATE TRIGGER trg_finance_import_historical_reprocess_receipt_before_update
BEFORE UPDATE ON finance_import_historical_reprocess_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_historical_reprocess_receipt_before_delete;
CREATE TRIGGER trg_finance_import_historical_reprocess_receipt_before_delete
BEFORE DELETE ON finance_import_historical_reprocess_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be deleted';

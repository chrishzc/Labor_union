-- Atomic workbook ingestion receipts. Formal accounting remains Preview/Apply owned.

CREATE TABLE IF NOT EXISTS finance_import_ingestion_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    batch_id BIGINT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_ingestion_receipt_key (idempotency_key),
    CONSTRAINT fk_finance_import_ingestion_receipt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_ingestion_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_content_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_ingestion_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_receipt_before_update;
CREATE TRIGGER trg_finance_import_ingestion_receipt_before_update
BEFORE UPDATE ON finance_import_ingestion_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_receipt_before_delete;
CREATE TRIGGER trg_finance_import_ingestion_receipt_before_delete
BEFORE DELETE ON finance_import_ingestion_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be deleted';

-- Append-only outcome ledger for every durable Finance Import ingestion command.

CREATE TABLE IF NOT EXISTS finance_import_ingestion_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    phase VARCHAR(64) NOT NULL,
    error_code VARCHAR(96) NULL,
    transaction_outcome ENUM('committed', 'rolled_back') NOT NULL,
    batch_id BIGINT NULL,
    started_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_attempt_command (idempotency_key),
    KEY ix_finance_import_attempt_digest (source_content_digest),
    CONSTRAINT fk_finance_import_attempt_batch
        FOREIGN KEY (batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_attempt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND source_content_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_finance_import_attempt_outcome
        CHECK (
            (transaction_outcome = 'committed' AND error_code IS NULL AND batch_id IS NOT NULL)
            OR (transaction_outcome = 'rolled_back' AND error_code IS NOT NULL AND batch_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_attempt_before_update;
CREATE TRIGGER trg_finance_import_ingestion_attempt_before_update
BEFORE UPDATE ON finance_import_ingestion_attempts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_attempts cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_ingestion_attempt_before_delete;
CREATE TRIGGER trg_finance_import_ingestion_attempt_before_delete
BEFORE DELETE ON finance_import_ingestion_attempts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_attempts cannot be deleted';

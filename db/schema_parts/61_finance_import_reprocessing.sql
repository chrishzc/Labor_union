-- Append-only audit for an explicitly requested historical finance reprocess.
-- The application inserts the completed run and its changed-row events in one
-- outer transaction. A dry run rolls that transaction back and leaves no IDs.
-- Add the replayable composite parent key used to prove that a referenced
-- import batch is completed. This changes no existing row values.
SET @finance_import_batch_status_key_exists = (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'finance_import_batches'
      AND INDEX_NAME = 'uq_finance_import_batch_id_status'
);
SET @finance_import_batch_status_key_ddl = IF(
    @finance_import_batch_status_key_exists = 0,
    'ALTER TABLE finance_import_batches ADD UNIQUE KEY uq_finance_import_batch_id_status (id, status)',
    'SELECT 1'
);
PREPARE add_finance_import_batch_status_key
    FROM @finance_import_batch_status_key_ddl;
EXECUTE add_finance_import_batch_status_key;
DEALLOCATE PREPARE add_finance_import_batch_status_key;


CREATE TABLE IF NOT EXISTS finance_import_reprocess_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    batch_status ENUM('staged', 'completed', 'failed')
        NOT NULL DEFAULT 'completed',
    actor VARCHAR(255) NOT NULL,
    classifier_version VARCHAR(191) NOT NULL,
    plan_fingerprint CHAR(64) NOT NULL,
    selected_count INT UNSIGNED NOT NULL,
    changed_count INT UNSIGNED NOT NULL,
    dispatch_count INT UNSIGNED NOT NULL,
    reconciled_count INT UNSIGNED NOT NULL,
    pending_count INT UNSIGNED NOT NULL,
    request_summary JSON NOT NULL,
    result_summary JSON NOT NULL,
    status ENUM('completed') NOT NULL DEFAULT 'completed',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_reprocess_run_plan (
        batch_id,
        plan_fingerprint
    ),
    INDEX idx_finance_import_reprocess_run_created (
        created_at,
        batch_id
    ),

    CONSTRAINT fk_finance_import_reprocess_run_batch
        FOREIGN KEY (batch_id, batch_status)
        REFERENCES finance_import_batches(id, status)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_reprocess_run_batch_completed CHECK (
        batch_status = 'completed'
    ),
    CONSTRAINT chk_finance_import_reprocess_run_actor CHECK (
        CHAR_LENGTH(TRIM(actor)) > 0
    ),
    CONSTRAINT chk_finance_import_reprocess_run_classifier CHECK (
        CHAR_LENGTH(TRIM(classifier_version)) > 0
    ),
    CONSTRAINT chk_finance_import_reprocess_run_fingerprint CHECK (
        plan_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_finance_import_reprocess_run_counts CHECK (
        changed_count <= selected_count
        AND dispatch_count <= changed_count
        AND reconciled_count <= dispatch_count
        AND pending_count <= dispatch_count
        AND reconciled_count + pending_count <= dispatch_count
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


DROP TRIGGER IF EXISTS trg_finance_import_reprocess_runs_before_update;
CREATE TRIGGER trg_finance_import_reprocess_runs_before_update
BEFORE UPDATE ON finance_import_reprocess_runs
FOR EACH ROW
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_import_reprocess_runs_before_delete;
CREATE TRIGGER trg_finance_import_reprocess_runs_before_delete
BEFORE DELETE ON finance_import_reprocess_runs
FOR EACH ROW
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be deleted';

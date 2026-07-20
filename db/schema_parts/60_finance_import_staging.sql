-- 每次 Excel 正規化結果的匯入批次；欄位名稱與 staging service 契約一致。
CREATE TABLE IF NOT EXISTS finance_import_batches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    format_id ENUM('legacy', 'taishin', 'sinopac') NOT NULL,
    source_file VARCHAR(1024) NULL COMMENT '空批次或過渡期多來源輸入允許 NULL',
    sheet_name VARCHAR(191) NOT NULL,
    header_row INT UNSIGNED NOT NULL,
    row_count INT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('staged', 'completed', 'failed') NOT NULL DEFAULT 'staged',
    failure_message TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,

    INDEX idx_finance_import_batch_status (status, created_at),
    CONSTRAINT chk_finance_import_batch_header_row CHECK (header_row >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 跨批次唯一的 canonical 銀行流水。
-- batch_id 與來源位置欄位保留給既有 staging writer；新流程的每次實際出現位置
-- 必須另外寫入 finance_import_occurrences。dedup_fingerprint 必須由正式指紋服務
-- 產生；既有資料若仍有 NULL，後續 ALTER 會明確失敗，不得以偽造值補齊。
CREATE TABLE IF NOT EXISTS finance_import_rows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dedup_fingerprint CHAR(64) NOT NULL,
    batch_id BIGINT NULL COMMENT '首度建立 canonical row 的相容批次；後續出現以 occurrence 為準',
    format_id ENUM('legacy', 'taishin', 'sinopac') NOT NULL,
    source_file VARCHAR(1024) NULL COMMENT '首度出現來源，相容既有 writer',
    source_bank_account VARCHAR(191) NULL,
    sheet_name VARCHAR(191) NULL COMMENT '首度出現工作表，相容既有 writer',
    source_row INT UNSIGNED NULL COMMENT '首度出現的一基底列號，相容既有 writer',
    source_reference VARCHAR(191) NULL COMMENT '銀行原始參考值；不承擔唯一性',
    transaction_date DATE NULL,
    transaction_time TIME NULL,
    posting_date DATE NULL,
    value_date DATE NULL,
    debit DECIMAL(18, 2) NULL,
    credit DECIMAL(18, 2) NULL,
    direction ENUM('incoming', 'outgoing', 'unknown') NOT NULL,
    balance DECIMAL(18, 2) NULL,
    currency VARCHAR(16) NULL,
    summary TEXT NULL,
    memo TEXT NULL,
    counterparty_name VARCHAR(255) NULL,
    counterparty_account VARCHAR(191) NULL,
    -- Parsed only from a supported source field.  The raw bank value above is
    -- intentionally preserved for audit and manual review.
    resolved_counterparty_account VARCHAR(191) NULL,
    cancellation_code VARCHAR(191) NULL,
    bank_references JSON NOT NULL,
    warnings JSON NOT NULL,
    raw_payload JSON NOT NULL,
    matched_identity_ids JSON NOT NULL DEFAULT (JSON_ARRAY()),

    classification_type VARCHAR(100) NOT NULL DEFAULT 'pending',
    classification_reason VARCHAR(255) NULL,
    classified_at TIMESTAMP NULL,
    reconciliation_status VARCHAR(50) NOT NULL DEFAULT 'pending',
    reconciliation_reference VARCHAR(191) NULL,
    reconciled_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_row_fingerprint (dedup_fingerprint),
    INDEX idx_finance_import_row_classification (
        classification_type,
        reconciliation_status
    ),
    INDEX idx_finance_import_row_account_date (
        source_bank_account,
        transaction_date
    ),

    CONSTRAINT fk_finance_import_row_compat_batch
        FOREIGN KEY (batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_row_fingerprint CHECK (
        dedup_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_finance_import_row_source_row CHECK (
        source_row IS NULL OR source_row >= 1
    ),
    CONSTRAINT chk_finance_import_row_amounts CHECK (
        (debit IS NULL OR debit >= 0)
        AND (credit IS NULL OR credit >= 0)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Idempotent upgrade for an existing staging table. MySQL rejects this ALTER
-- when any legacy row still has a NULL fingerprint, forcing explicit data
-- review instead of manufacturing an identifier. Replaying it after a
-- successful upgrade is harmless.
ALTER TABLE finance_import_rows
    MODIFY COLUMN dedup_fingerprint CHAR(64) NOT NULL;


-- Additive, replayable upgrade for databases created before the resolved
-- account was introduced.  MySQL versions used by this project do not all
-- support ADD COLUMN IF NOT EXISTS, so use dynamic DDL after a metadata check.
-- Existing canonical rows deliberately remain NULL: this schema migration must
-- never infer or backfill a bank account.
SET @resolved_counterparty_account_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'finance_import_rows'
      AND COLUMN_NAME = 'resolved_counterparty_account'
);
SET @resolved_counterparty_account_ddl = IF(
    @resolved_counterparty_account_exists = 0,
    'ALTER TABLE finance_import_rows ADD COLUMN resolved_counterparty_account VARCHAR(191) NULL AFTER counterparty_account',
    'SELECT 1'
);
PREPARE add_resolved_counterparty_account FROM @resolved_counterparty_account_ddl;
EXECUTE add_resolved_counterparty_account;
DEALLOCATE PREPARE add_resolved_counterparty_account;


-- canonical 流水在每個來源檔／批次中的實際出現位置。
CREATE TABLE IF NOT EXISTS finance_import_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    source_file VARCHAR(1024) NULL,
    sheet_name VARCHAR(191) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    warnings JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_import_occurrence_position (
        batch_id,
        sheet_name,
        source_row
    ),
    INDEX idx_finance_import_occurrence_row (finance_import_row_id, batch_id),

    CONSTRAINT fk_finance_import_occurrence_batch
        FOREIGN KEY (batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_occurrence_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_occurrence_source_row CHECK (source_row >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

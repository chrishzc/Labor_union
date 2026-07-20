-- 已唯一匹配正式申請批次的政府補助銀行事件。
-- 未唯一匹配的銀行流水只保留於 finance_import_rows，不建立本表資料。
-- 複合 FK 需要 claim item 提供 id + batch_id 候選鍵；以名稱守門使 loader 可重跑。
SET @gov_subsidy_allocation_table_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
);

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'subsidy_claim_batch_items'
      AND INDEX_NAME = 'uq_subsidy_claim_item_id_batch'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `subsidy_claim_batch_items` ADD UNIQUE KEY `uq_subsidy_claim_item_id_batch` (`id`, `batch_id`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

CREATE TABLE IF NOT EXISTS government_subsidy_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    claim_batch_id BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    transaction_type ENUM('receipt', 'reversal') NOT NULL,
    transaction_status ENUM('succeeded', 'failed', 'reversed')
        NOT NULL DEFAULT 'succeeded',
    amount DECIMAL(18, 2) NOT NULL,
    occurred_at DATE NULL,
    external_reference VARCHAR(191) NOT NULL,
    reversal_of_transaction_id BIGINT NULL,
    reversal_target_type ENUM('receipt', 'reversal') NOT NULL DEFAULT 'receipt',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_government_subsidy_transaction_import_row (
        finance_import_row_id
    ),
    UNIQUE KEY uq_government_subsidy_transaction_reference (
        external_reference
    ),
    UNIQUE KEY uq_government_subsidy_transaction_id_batch (
        id,
        claim_batch_id
    ),
    UNIQUE KEY uq_government_subsidy_transaction_reversal_target (
        id,
        claim_batch_id,
        transaction_type
    ),
    INDEX idx_government_subsidy_transaction_batch (
        claim_batch_id,
        occurred_at
    ),
    INDEX idx_government_subsidy_transaction_reversal (
        reversal_of_transaction_id
    ),

    CONSTRAINT fk_government_subsidy_transaction_batch
        FOREIGN KEY (claim_batch_id)
        REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_transaction_import_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_transaction_reversal_receipt
        FOREIGN KEY (reversal_of_transaction_id, claim_batch_id, reversal_target_type)
        REFERENCES government_subsidy_transactions(id, claim_batch_id, transaction_type)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT chk_government_subsidy_transaction_amount
        CHECK (amount > 0),
    CONSTRAINT chk_government_subsidy_transaction_succeeded_date
        CHECK (transaction_status <> 'succeeded' OR occurred_at IS NOT NULL),
    CONSTRAINT chk_government_subsidy_transaction_original
        CHECK (
            (transaction_type = 'receipt' AND reversal_of_transaction_id IS NULL)
            OR
            (transaction_type = 'reversal' AND reversal_of_transaction_id IS NOT NULL)
        ),
    CONSTRAINT chk_government_subsidy_transaction_reversal_target
        CHECK (reversal_target_type = 'receipt')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 將複合同批次約束補到既有表；每一步獨立守門，中斷後仍可重跑。
SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND COLUMN_NAME = 'reversal_target_type'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD COLUMN `reversal_target_type` ENUM(''receipt'', ''reversal'') NOT NULL DEFAULT ''receipt'' AFTER `reversal_of_transaction_id`',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND INDEX_NAME = 'uq_government_subsidy_transaction_id_batch'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD UNIQUE KEY `uq_government_subsidy_transaction_id_batch` (`id`, `claim_batch_id`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND INDEX_NAME = 'uq_government_subsidy_transaction_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD UNIQUE KEY `uq_government_subsidy_transaction_reversal_target` (`id`, `claim_batch_id`, `transaction_type`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND CONSTRAINT_NAME = 'chk_government_subsidy_transaction_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD CONSTRAINT `chk_government_subsidy_transaction_reversal_target` CHECK (`reversal_target_type` = ''receipt'')',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_transactions'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_transaction_reversal_receipt'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_transactions` ADD CONSTRAINT `fk_government_subsidy_transaction_reversal_receipt` FOREIGN KEY (`reversal_of_transaction_id`, `claim_batch_id`, `reversal_target_type`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`, `transaction_type`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND COLUMN_NAME = 'reversal_target_type'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD COLUMN `reversal_target_type` ENUM(''receipt'', ''reversal'') NOT NULL DEFAULT ''receipt'' AFTER `reversal_of_allocation_id`',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND INDEX_NAME = 'uq_government_subsidy_allocation_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD UNIQUE KEY `uq_government_subsidy_allocation_reversal_target` (`id`, `claim_batch_id`, `allocation_type`)',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'chk_government_subsidy_allocation_reversal_target'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `chk_government_subsidy_allocation_reversal_target` CHECK (`reversal_target_type` = ''receipt'')',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_allocation_transaction_batch'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `fk_government_subsidy_allocation_transaction_batch` FOREIGN KEY (`transaction_id`, `claim_batch_id`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_allocation_item_batch'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `fk_government_subsidy_allocation_item_batch` FOREIGN KEY (`claim_item_id`, `claim_batch_id`) REFERENCES `subsidy_claim_batch_items` (`id`, `batch_id`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;

SET @gov_subsidy_schema_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'government_subsidy_allocations'
      AND CONSTRAINT_NAME = 'fk_government_subsidy_allocation_reversal_receipt'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @gov_subsidy_schema_sql = IF(
    @gov_subsidy_allocation_table_exists = 1 AND @gov_subsidy_schema_exists = 0,
    'ALTER TABLE `government_subsidy_allocations` ADD CONSTRAINT `fk_government_subsidy_allocation_reversal_receipt` FOREIGN KEY (`reversal_of_allocation_id`, `claim_batch_id`, `reversal_target_type`) REFERENCES `government_subsidy_allocations` (`id`, `claim_batch_id`, `allocation_type`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE gov_subsidy_schema_stmt FROM @gov_subsidy_schema_sql;
EXECUTE gov_subsidy_schema_stmt;
DEALLOCATE PREPARE gov_subsidy_schema_stmt;


-- 政府入款逐筆分配至同一申請批次的案件／服務指派明細。
-- requested_amount 與 approved_amount 屬申請快照，不由本表覆寫。
CREATE TABLE IF NOT EXISTS government_subsidy_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_id BIGINT NOT NULL,
    claim_batch_id BIGINT NOT NULL,
    claim_item_id BIGINT NOT NULL,
    allocation_type ENUM('receipt', 'reversal') NOT NULL DEFAULT 'receipt',
    allocated_amount DECIMAL(18, 2) NOT NULL,
    reversal_of_allocation_id BIGINT NULL,
    reversal_target_type ENUM('receipt', 'reversal') NOT NULL DEFAULT 'receipt',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_government_subsidy_allocation_target (
        transaction_id,
        claim_item_id
    ),
    UNIQUE KEY uq_government_subsidy_allocation_reversal_target (
        id,
        claim_batch_id,
        allocation_type
    ),
    INDEX idx_government_subsidy_allocation_batch_item (
        claim_batch_id,
        claim_item_id
    ),
    INDEX idx_government_subsidy_allocation_reversal (
        reversal_of_allocation_id
    ),

    CONSTRAINT fk_government_subsidy_allocation_transaction_batch
        FOREIGN KEY (transaction_id, claim_batch_id)
        REFERENCES government_subsidy_transactions(id, claim_batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_allocation_batch
        FOREIGN KEY (claim_batch_id)
        REFERENCES subsidy_claim_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_allocation_item_batch
        FOREIGN KEY (claim_item_id, claim_batch_id)
        REFERENCES subsidy_claim_batch_items(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_allocation_reversal_receipt
        FOREIGN KEY (reversal_of_allocation_id, claim_batch_id, reversal_target_type)
        REFERENCES government_subsidy_allocations(id, claim_batch_id, allocation_type)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT chk_government_subsidy_allocation_amount
        CHECK (allocated_amount > 0),
    CONSTRAINT chk_government_subsidy_allocation_original
        CHECK (
            (allocation_type = 'receipt' AND reversal_of_allocation_id IS NULL)
            OR
            (allocation_type = 'reversal' AND reversal_of_allocation_id IS NOT NULL)
        ),
    CONSTRAINT chk_government_subsidy_allocation_reversal_target
        CHECK (reversal_target_type = 'receipt')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

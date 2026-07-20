-- 讓客戶實際金流可追溯至 canonical 銀行流水。
-- 既有與人工補登交易允許 NULL；使用 INFORMATION_SCHEMA 讓 migration 可重跑。
SET @client_payment_finance_link_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payment_transactions'
      AND COLUMN_NAME = 'finance_import_row_id'
);
SET @client_payment_finance_link_sql = IF(
    @client_payment_finance_link_column_exists = 0,
    'ALTER TABLE `client_payment_transactions` ADD COLUMN `finance_import_row_id` BIGINT NULL COMMENT ''canonical 銀行流水；人工補登允許 NULL'' AFTER `external_reference`',
    'SELECT 1'
);
PREPARE client_payment_finance_link_stmt FROM @client_payment_finance_link_sql;
EXECUTE client_payment_finance_link_stmt;
DEALLOCATE PREPARE client_payment_finance_link_stmt;

SET @client_payment_finance_link_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payment_transactions'
      AND INDEX_NAME = 'idx_client_payment_tx_finance_import_row'
);
SET @client_payment_finance_link_sql = IF(
    @client_payment_finance_link_index_exists = 0,
    'ALTER TABLE `client_payment_transactions` ADD INDEX `idx_client_payment_tx_finance_import_row` (`finance_import_row_id`)',
    'SELECT 1'
);
PREPARE client_payment_finance_link_stmt FROM @client_payment_finance_link_sql;
EXECUTE client_payment_finance_link_stmt;
DEALLOCATE PREPARE client_payment_finance_link_stmt;

SET @client_payment_finance_link_fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payment_transactions'
      AND CONSTRAINT_NAME = 'fk_client_payment_tx_finance_import_row'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @client_payment_finance_link_sql = IF(
    @client_payment_finance_link_fk_exists = 0,
    'ALTER TABLE `client_payment_transactions` ADD CONSTRAINT `fk_client_payment_tx_finance_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE client_payment_finance_link_stmt FROM @client_payment_finance_link_sql;
EXECUTE client_payment_finance_link_stmt;
DEALLOCATE PREPARE client_payment_finance_link_stmt;

-- 既有客戶帳務表補上補助退款人工覆核欄位。
-- 使用 INFORMATION_SCHEMA 逐欄檢查，確保 migration 可安全重跑且不改寫歷史資料。
SET @subsidy_return_review_status_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payments'
      AND COLUMN_NAME = 'subsidy_return_review_status'
);
SET @subsidy_return_review_sql = IF(
    @subsidy_return_review_status_exists = 0,
    'ALTER TABLE `client_payments` ADD COLUMN `subsidy_return_review_status` ENUM(''review_required'') NULL COMMENT ''補助退還人工覆核狀態；NULL 表示未暫停自動核銷'' AFTER `subsidy_return_at`',
    'SELECT 1'
);
PREPARE subsidy_return_review_stmt FROM @subsidy_return_review_sql;
EXECUTE subsidy_return_review_stmt;
DEALLOCATE PREPARE subsidy_return_review_stmt;

SET @subsidy_return_review_reason_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_payments'
      AND COLUMN_NAME = 'subsidy_return_review_reason'
);
SET @subsidy_return_review_sql = IF(
    @subsidy_return_review_reason_exists = 0,
    'ALTER TABLE `client_payments` ADD COLUMN `subsidy_return_review_reason` TEXT NULL COMMENT ''補助退還需人工覆核的原因'' AFTER `subsidy_return_review_status`',
    'SELECT 1'
);
PREPARE subsidy_return_review_stmt FROM @subsidy_return_review_sql;
EXECUTE subsidy_return_review_stmt;
DEALLOCATE PREPARE subsidy_return_review_stmt;

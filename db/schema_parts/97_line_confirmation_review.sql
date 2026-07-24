-- 第五階段 5.6：人工審查處理者、原因與查詢索引。
-- 使用 INFORMATION_SCHEMA 守門，使既有開發資料庫可重複執行 init_db.py。
SET @line_review_admin_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND COLUMN_NAME = 'reviewed_by_admin_user_id'
);
SET @line_review_schema_sql = IF(
    @line_review_admin_column_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD COLUMN `reviewed_by_admin_user_id` BIGINT NULL COMMENT ''Web 管理中心處理者；開發終端處理時可為 NULL'' AFTER `status`',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_reason_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND COLUMN_NAME = 'decision_reason'
);
SET @line_review_schema_sql = IF(
    @line_review_reason_column_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD COLUMN `decision_reason` TEXT NULL COMMENT ''核准備註或拒絕原因'' AFTER `reviewed_by_line_user_id`',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_status_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND INDEX_NAME = 'idx_confirmation_status_time'
);
SET @line_review_schema_sql = IF(
    @line_review_status_index_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD INDEX `idx_confirmation_status_time` (`status`, `created_at`)',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_admin_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND INDEX_NAME = 'idx_confirmation_admin_reviewer'
);
SET @line_review_schema_sql = IF(
    @line_review_admin_index_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD INDEX `idx_confirmation_admin_reviewer` (`reviewed_by_admin_user_id`, `reviewed_at`)',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

SET @line_review_admin_fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_confirmation_requests'
      AND CONSTRAINT_NAME = 'fk_confirmation_admin_reviewer'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @line_review_schema_sql = IF(
    @line_review_admin_fk_exists = 0,
    'ALTER TABLE `line_confirmation_requests` ADD CONSTRAINT `fk_confirmation_admin_reviewer` FOREIGN KEY (`reviewed_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL',
    'SELECT 1'
);
PREPARE line_review_schema_stmt FROM @line_review_schema_sql;
EXECUTE line_review_schema_stmt;
DEALLOCATE PREPARE line_review_schema_stmt;

-- Add the explicit resume-delivery fact used by resume commands and DOC-SEND-001.
-- Existing matching rows deliberately remain NULL; no delivery is inferred.

SET @matching_resume_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @matching_resume_required_columns = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME IN (
          'id', 'case_no', 'staff_id', 'caregiver_accepted',
          'sent_at', 'replied_at', 'sent_info_1_at', 'sent_info_2_at'
      )
);
SET @matching_resume_sql = IF(
    @matching_resume_table_exists = 1
    AND @matching_resume_required_columns = 8,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_MATCHING_RECORDS_PREREQUISITE_INVALID`'
);
PREPARE matching_resume_stmt FROM @matching_resume_sql;
EXECUTE matching_resume_stmt;
DEALLOCATE PREPARE matching_resume_stmt;

SET @matching_resume_column_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME = 'sent_resume_at'
);
SET @matching_resume_column_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME = 'sent_resume_at'
      AND DATA_TYPE = 'datetime'
      AND COLUMN_TYPE = 'datetime'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
      AND COALESCE(GENERATION_EXPRESSION, '') = ''
);
SET @matching_resume_sql = IF(
    @matching_resume_column_any = 0,
    'ALTER TABLE `matching_records`
       ADD COLUMN `sent_resume_at` DATETIME NULL
       COMMENT ''履歷發送給客戶的時間；NULL 表示無明確發送事實''
       AFTER `sent_info_2_at`',
    IF(
        @matching_resume_column_any = 1
        AND @matching_resume_column_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SENT_RESUME_AT_INVALID_SPEC`'
    )
);
PREPARE matching_resume_stmt FROM @matching_resume_sql;
EXECUTE matching_resume_stmt;
DEALLOCATE PREPARE matching_resume_stmt;

SET @matching_resume_column_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'matching_records'
      AND COLUMN_NAME = 'sent_resume_at'
      AND DATA_TYPE = 'datetime'
      AND COLUMN_TYPE = 'datetime'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
      AND COALESCE(GENERATION_EXPRESSION, '') = ''
);
SET @matching_resume_sql = IF(
    @matching_resume_column_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SENT_RESUME_AT_POSTCHECK_FAILED`'
);
PREPARE matching_resume_stmt FROM @matching_resume_sql;
EXECUTE matching_resume_stmt;
DEALLOCATE PREPARE matching_resume_stmt;

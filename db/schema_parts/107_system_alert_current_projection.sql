-- Preserve legacy system_alerts rows while installing the mutable current
-- projection required by SystemAlertService. This migration is candidate-only.

SET @system_alert_table_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @system_alert_sql = IF(
    @system_alert_table_exists = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_TABLE_NOT_FOUND`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_new_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND COLUMN_NAME IN (
          'alert_code', 'source_domain', 'case_key', 'reason', 'details',
          'claimed_by', 'claimed_at', 'resolution_reason', 'updated_at'
      )
);
SET @system_alert_legacy_shape_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND (
          (COLUMN_NAME = 'id' AND COLUMN_TYPE = 'int'
              AND IS_NULLABLE = 'NO' AND EXTRA LIKE '%auto_increment%')
          OR (COLUMN_NAME = 'event_type' AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'description' AND COLUMN_TYPE = 'text'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'status'
              AND COLUMN_TYPE = 'enum(''pending'',''resolved'')')
          OR (COLUMN_NAME = 'created_at' AND DATA_TYPE = 'timestamp')
          OR (COLUMN_NAME = 'resolved_at' AND DATA_TYPE = 'timestamp')
          OR (COLUMN_NAME = 'resolved_by' AND COLUMN_TYPE = 'varchar(50)')
      )
);
SET @system_alert_migrate_legacy = (
    @system_alert_new_column_count = 0
    AND @system_alert_legacy_shape_count = 7
);
SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1
    OR @system_alert_new_column_count = 9,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_PARTIAL_OR_DRIFTED_SHAPE`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'ALTER TABLE `system_alerts`
       ADD COLUMN `alert_code` VARCHAR(50) NULL AFTER `id`,
       ADD COLUMN `source_domain` VARCHAR(50) NULL AFTER `alert_code`,
       ADD COLUMN `case_key` VARCHAR(100) NULL AFTER `source_domain`,
       ADD COLUMN `reason` VARCHAR(500) NULL AFTER `case_key`,
       ADD COLUMN `details` JSON NULL AFTER `reason`,
       ADD COLUMN `claimed_by` VARCHAR(100) NULL AFTER `status`,
       ADD COLUMN `claimed_at` DATETIME NULL AFTER `claimed_by`,
       ADD COLUMN `resolution_reason` VARCHAR(500) NULL AFTER `resolved_by`,
       ADD COLUMN `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
         ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'ALTER TABLE `system_alerts`
       MODIFY COLUMN `status`
         ENUM(''pending'',''open'',''claimed'',''resolved'')
         NULL DEFAULT ''pending''',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'UPDATE `system_alerts`
        SET `alert_code` = COALESCE(NULLIF(TRIM(`event_type`), ''''), ''LEGACY''),
            `source_domain` = ''LEGACY'',
            `case_key` = CONCAT(''legacy-alert:'', `id`),
            `reason` = COALESCE(
                NULLIF(LEFT(TRIM(`description`), 500), ''''),
                ''Legacy system alert''
            ),
            `details` = JSON_OBJECT(
                ''legacy_event_type'', COALESCE(NULLIF(TRIM(`event_type`), ''''), ''LEGACY''),
                ''migration'', ''system_alert_current_projection_v1''
            ),
            `status` = IF(`status` = ''pending'', ''open'', ''resolved'')',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_invalid_rows = (
    SELECT COUNT(*)
    FROM system_alerts
    WHERE alert_code IS NULL
       OR source_domain IS NULL
       OR case_key IS NULL
       OR reason IS NULL
       OR details IS NULL
       OR status NOT IN ('open', 'claimed', 'resolved')
);
SET @system_alert_duplicate_identity = (
    SELECT COUNT(*)
    FROM (
        SELECT alert_code, case_key
        FROM system_alerts
        GROUP BY alert_code, case_key
        HAVING COUNT(*) > 1
    ) AS duplicate_identity
);
SET @system_alert_sql = IF(
    @system_alert_invalid_rows = 0
    AND @system_alert_duplicate_identity = 0,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_BACKFILL_VALIDATION_FAILED`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_sql = IF(
    @system_alert_migrate_legacy = 1,
    'ALTER TABLE `system_alerts`
       MODIFY COLUMN `alert_code` VARCHAR(50) NOT NULL,
       MODIFY COLUMN `source_domain` VARCHAR(50) NOT NULL,
       MODIFY COLUMN `case_key` VARCHAR(100) NOT NULL,
       MODIFY COLUMN `reason` VARCHAR(500) NOT NULL,
       MODIFY COLUMN `details` JSON NOT NULL,
       MODIFY COLUMN `status`
         ENUM(''open'',''claimed'',''resolved'') NOT NULL DEFAULT ''open'',
       MODIFY COLUMN `event_type` VARCHAR(50) NULL,
       MODIFY COLUMN `description` TEXT NULL,
       MODIFY COLUMN `resolved_by` VARCHAR(100) NULL,
       MODIFY COLUMN `resolved_at` DATETIME NULL,
       MODIFY COLUMN `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
       MODIFY COLUMN `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
         ON UPDATE CURRENT_TIMESTAMP',
    'SELECT 1'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_uq_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND INDEX_NAME = 'uq_alert_case'
);
SET @system_alert_uq_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'uq_alert_case'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 0
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) =
               'alert_code,case_key'
    ) AS exact_index
);
SET @system_alert_sql = IF(
    @system_alert_uq_any = 0,
    'ALTER TABLE `system_alerts`
       ADD UNIQUE KEY `uq_alert_case` (`alert_code`, `case_key`)',
    IF(
        @system_alert_uq_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_UNIQUE_INDEX_DRIFT`'
    )
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_status_index_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND INDEX_NAME = 'idx_system_alert_status'
);
SET @system_alert_status_index_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'idx_system_alert_status'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 1
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) = 'status'
    ) AS exact_index
);
SET @system_alert_sql = IF(
    @system_alert_status_index_any = 0,
    'ALTER TABLE `system_alerts`
       ADD INDEX `idx_system_alert_status` (`status`)',
    IF(
        @system_alert_status_index_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_STATUS_INDEX_DRIFT`'
    )
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

SET @system_alert_uq_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'uq_alert_case'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 0
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) =
               'alert_code,case_key'
    ) AS exact_index
);
SET @system_alert_status_index_exact = (
    SELECT COUNT(*)
    FROM (
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'system_alerts'
          AND INDEX_NAME = 'idx_system_alert_status'
        GROUP BY INDEX_NAME, NON_UNIQUE
        HAVING NON_UNIQUE = 1
           AND GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) = 'status'
    ) AS exact_index
);
SET @system_alert_current_shape_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'system_alerts'
      AND (
          (COLUMN_NAME = 'alert_code' AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'source_domain' AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'case_key' AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'reason' AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'details' AND DATA_TYPE = 'json'
              AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'status'
              AND COLUMN_TYPE = 'enum(''open'',''claimed'',''resolved'')'
              AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'open')
          OR (COLUMN_NAME = 'claimed_by' AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'claimed_at' AND DATA_TYPE = 'datetime'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'resolved_by' AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'resolved_at' AND DATA_TYPE = 'datetime'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'resolution_reason' AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'created_at' AND DATA_TYPE = 'timestamp')
          OR (COLUMN_NAME = 'updated_at' AND DATA_TYPE = 'timestamp')
      )
);
SET @system_alert_sql = IF(
    @system_alert_current_shape_count = 13
    AND @system_alert_uq_exact = 1
    AND @system_alert_status_index_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_SYSTEM_ALERTS_CURRENT_SHAPE_INVALID`'
);
PREPARE system_alert_stmt FROM @system_alert_sql;
EXECUTE system_alert_stmt;
DEALLOCATE PREPARE system_alert_stmt;

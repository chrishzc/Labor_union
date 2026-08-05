-- Add canonical per-order service-time terms without interpreting legacy free text.
-- Existing orders deliberately remain NULL and must be completed by an explicit command.

SET @order_service_terms_orders_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @order_service_terms_prereq_sql = IF(
    @order_service_terms_orders_exists = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDERS_TABLE_NOT_FOUND`'
);
PREPARE order_service_terms_stmt FROM @order_service_terms_prereq_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_start_time_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_start_time'
);
SET @order_service_start_time_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_start_time'
      AND DATA_TYPE = 'time'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
);
SET @order_service_terms_sql = IF(
    @order_service_start_time_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `service_start_time` TIME NULL COMMENT ''案件統一每日服務開始時間；既有案件待明確補登'' AFTER `actual_end_date`',
    IF(
        @order_service_start_time_any = 1
        AND @order_service_start_time_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_START_TIME_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_end_time_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_time'
);
SET @order_service_end_time_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_time'
      AND DATA_TYPE = 'time'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
);
SET @order_service_terms_sql = IF(
    @order_service_end_time_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `service_end_time` TIME NULL COMMENT ''案件統一每日服務結束時間；既有案件待明確補登'' AFTER `service_start_time`',
    IF(
        @order_service_end_time_any = 1
        AND @order_service_end_time_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_END_TIME_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_end_offset_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_day_offset'
);
SET @order_service_end_offset_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'service_end_day_offset'
      AND DATA_TYPE = 'tinyint'
      AND COLUMN_TYPE = 'tinyint unsigned'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
);
SET @order_service_terms_sql = IF(
    @order_service_end_offset_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `service_end_day_offset` TINYINT UNSIGNED NULL COMMENT ''0=服務日當日結束，1=次日結束；不得由時間大小推測'' AFTER `service_end_time`',
    IF(
        @order_service_end_offset_any = 1
        AND @order_service_end_offset_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_END_DAY_OFFSET_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_terms_complete_check_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND CONSTRAINT_NAME = 'chk_orders_service_time_terms_complete'
      AND CONSTRAINT_TYPE = 'CHECK'
);
SET @order_service_terms_complete_check_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'orders'
      AND tc.CONSTRAINT_NAME = 'chk_orders_service_time_terms_complete'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND LOWER(
          REPLACE(
              REPLACE(
                  REPLACE(
                      REPLACE(
                          REPLACE(
                              REPLACE(
                                  REPLACE(cc.CHECK_CLAUSE, '`', ''),
                                  ' ',
                                  ''
                              ),
                              CHAR(9),
                              ''
                          ),
                          CHAR(10),
                          ''
                      ),
                      CHAR(13),
                      ''
                  ),
                  '(',
                  ''
              ),
              ')',
              ''
          )
      ) = 'service_start_timeisnullandservice_end_timeisnullandservice_end_day_offsetisnullorservice_start_timeisnotnullandservice_end_timeisnotnullandservice_end_day_offsetisnotnull'
);
SET @order_service_terms_sql = IF(
    @order_service_terms_complete_check_any = 0,
    'ALTER TABLE `orders` ADD CONSTRAINT `chk_orders_service_time_terms_complete` CHECK ((`service_start_time` IS NULL AND `service_end_time` IS NULL AND `service_end_day_offset` IS NULL) OR (`service_start_time` IS NOT NULL AND `service_end_time` IS NOT NULL AND `service_end_day_offset` IS NOT NULL))',
    IF(
        @order_service_terms_complete_check_any = 1
        AND @order_service_terms_complete_check_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_TIME_TERMS_COMPLETE_CHECK_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

SET @order_service_end_offset_check_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND CONSTRAINT_NAME = 'chk_orders_service_end_day_offset'
      AND CONSTRAINT_TYPE = 'CHECK'
);
SET @order_service_end_offset_check_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'orders'
      AND tc.CONSTRAINT_NAME = 'chk_orders_service_end_day_offset'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND LOWER(
          REPLACE(
              REPLACE(
                  REPLACE(
                      REPLACE(
                          REPLACE(
                              REPLACE(
                                  REPLACE(cc.CHECK_CLAUSE, '`', ''),
                                  ' ',
                                  ''
                              ),
                              CHAR(9),
                              ''
                          ),
                          CHAR(10),
                          ''
                      ),
                      CHAR(13),
                      ''
                  ),
                  '(',
                  ''
              ),
              ')',
              ''
          )
      ) = 'service_end_day_offsetisnullorservice_end_day_offsetin0,1'
);
SET @order_service_terms_sql = IF(
    @order_service_end_offset_check_any = 0,
    'ALTER TABLE `orders` ADD CONSTRAINT `chk_orders_service_end_day_offset` CHECK (`service_end_day_offset` IS NULL OR `service_end_day_offset` IN (0, 1))',
    IF(
        @order_service_end_offset_check_any = 1
        AND @order_service_end_offset_check_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_SERVICE_END_DAY_OFFSET_CHECK_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE order_service_terms_stmt FROM @order_service_terms_sql;
EXECUTE order_service_terms_stmt;
DEALLOCATE PREPARE order_service_terms_stmt;

-- Canonical ORD-01 aggregate revision, explicit control facts and alert outbox.
-- This migration is additive and never infers facts from existing order rows.

SET @olcf_orders_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @olcf_history_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_state_events'
      AND TABLE_TYPE = 'BASE TABLE'
);
SET @olcf_service_terms_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND (
          (
              COLUMN_NAME IN ('service_start_time', 'service_end_time')
              AND DATA_TYPE = 'time'
              AND IS_NULLABLE = 'YES'
              AND COLUMN_DEFAULT IS NULL
          )
          OR
          (
              COLUMN_NAME = 'service_end_day_offset'
              AND DATA_TYPE = 'tinyint'
              AND COLUMN_TYPE = 'tinyint unsigned'
              AND IS_NULLABLE = 'YES'
              AND COLUMN_DEFAULT IS NULL
          )
      )
);
SET @olcf_prereq_sql = IF(
    @olcf_orders_exists != 1,
    'SELECT * FROM `FAIL_CLOSED_ORDERS_TABLE_NOT_FOUND`',
    IF(
        @olcf_history_exists != 1,
        'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_STATE_EVENTS_TABLE_NOT_FOUND`',
        IF(
            @olcf_service_terms_exact != 3,
            'SELECT * FROM `FAIL_CLOSED_ORDER_SERVICE_TIME_TERMS_INVALID_OR_MISSING`',
            'SELECT 1'
        )
    )
);
PREPARE olcf_stmt FROM @olcf_prereq_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_version_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'lifecycle_version'
);
SET @olcf_version_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders'
      AND COLUMN_NAME = 'lifecycle_version'
      AND DATA_TYPE = 'bigint'
      AND COLUMN_TYPE = 'bigint unsigned'
      AND IS_NULLABLE = 'NO'
      AND COLUMN_DEFAULT = '0'
);
SET @olcf_version_sql = IF(
    @olcf_version_any = 0,
    'ALTER TABLE `orders` ADD COLUMN `lifecycle_version` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT ''ORD-01 aggregate revision；每個非 replay command 恰遞增一次'' AFTER `status`',
    IF(
        @olcf_version_any = 1 AND @olcf_version_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_VERSION_INVALID_SPEC_REVIEW_REQUIRED`'
    )
);
PREPARE olcf_stmt FROM @olcf_version_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_events_preexisting = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
);

CREATE TABLE IF NOT EXISTS order_lifecycle_control_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL,
    control_type ENUM(
        'cancellation',
        'actual_start_reconfirmation',
        'human_hold'
    ) NOT NULL,
    control_key VARCHAR(100) NOT NULL,
    scope ENUM('order', 'enter_service', 'auto_complete') NOT NULL,
    action ENUM('activate', 'clear') NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_hash CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_snapshot JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_lifecycle_control_event_idempotency (
        case_no,
        idempotency_key
    ),
    UNIQUE KEY uq_order_lifecycle_control_event_identity (
        id,
        case_no,
        control_type,
        control_key
    ),
    INDEX idx_order_lifecycle_control_event_case_type_time (
        case_no,
        control_type,
        control_key,
        created_at
    ),
    CONSTRAINT fk_order_lifecycle_control_event_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_control_event_text
        CHECK (
            CHAR_LENGTH(TRIM(control_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_control_event_payload
        CHECK (
            payload_hash REGEXP '^[0-9a-f]{64}$'
            AND JSON_TYPE(payload_snapshot) = 'OBJECT'
        ),
    CONSTRAINT chk_order_lifecycle_control_event_shape
        CHECK (
            (
                control_type = 'cancellation'
                AND control_key = 'order_cancelled'
                AND scope = 'order'
            )
            OR
            (
                control_type = 'actual_start_reconfirmation'
                AND control_key = 'actual_start_reconfirmation'
                AND scope = 'enter_service'
            )
            OR
            (
                control_type = 'human_hold'
                AND scope IN ('enter_service', 'auto_complete')
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @olcf_events_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
);
SET @olcf_events_columns_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
      AND (
          (
              COLUMN_NAME = 'id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
              AND EXTRA = 'auto_increment'
          )
          OR
          (
              COLUMN_NAME = 'case_no'
              AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_type'
              AND COLUMN_TYPE = 'enum(''cancellation'',''actual_start_reconfirmation'',''human_hold'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_key'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'scope'
              AND COLUMN_TYPE = 'enum(''order'',''enter_service'',''auto_complete'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'action'
              AND COLUMN_TYPE = 'enum(''activate'',''clear'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'actor'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'reason'
              AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'expected_version'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'idempotency_key'
              AND COLUMN_TYPE = 'varchar(191)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'payload_hash'
              AND COLUMN_TYPE = 'char(64)'
              AND IS_NULLABLE = 'NO'
              AND CHARACTER_SET_NAME = 'ascii'
              AND COLLATION_NAME = 'ascii_bin'
          )
          OR
          (
              COLUMN_NAME = 'payload_snapshot'
              AND DATA_TYPE = 'json'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'created_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
          )
      )
);
SET @olcf_events_index_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
      AND (
          (
              INDEX_NAME = 'PRIMARY'
              AND NON_UNIQUE = 0
              AND SEQ_IN_INDEX = 1
              AND COLUMN_NAME = 'id'
          )
          OR
          (
              INDEX_NAME = 'uq_order_lifecycle_control_event_idempotency'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'idempotency_key')
              )
          )
          OR
          (
              INDEX_NAME = 'uq_order_lifecycle_control_event_identity'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'id')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 4 AND COLUMN_NAME = 'control_key')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_control_event_case_type_time'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_key')
                  OR
                  (SEQ_IN_INDEX = 4 AND COLUMN_NAME = 'created_at')
              )
          )
      )
);
SET @olcf_events_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_control_events'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_control_event_case'
      AND k.COLUMN_NAME = 'case_no'
      AND k.REFERENCED_TABLE_NAME = 'orders'
      AND k.REFERENCED_COLUMN_NAME = 'case_no'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_events_checks_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'order_lifecycle_control_events'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_event_text'
              AND cc.CHECK_CLAUSE LIKE '%control_key%'
              AND cc.CHECK_CLAUSE LIKE '%actor%'
              AND cc.CHECK_CLAUSE LIKE '%reason%'
              AND cc.CHECK_CLAUSE LIKE '%idempotency_key%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_event_payload'
              AND cc.CHECK_CLAUSE LIKE '%payload_hash%'
              AND cc.CHECK_CLAUSE LIKE '%payload_snapshot%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_event_shape'
              AND cc.CHECK_CLAUSE LIKE '%order_cancelled%'
              AND cc.CHECK_CLAUSE LIKE '%actual_start_reconfirmation%'
              AND cc.CHECK_CLAUSE LIKE '%human_hold%'
          )
      )
);
SET @olcf_events_table_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_events'
      AND ENGINE = 'InnoDB'
      AND TABLE_COLLATION = 'utf8mb4_unicode_ci'
);
SET @olcf_events_metadata_sql = IF(
    @olcf_events_column_count = 13
    AND @olcf_events_columns_exact = 13
    AND @olcf_events_index_parts_exact = 11
    AND @olcf_events_fk_exact = 1
    AND @olcf_events_checks_exact = 3
    AND @olcf_events_table_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_EVENTS_METADATA_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_events_metadata_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_events_update_trigger_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND TRIGGER_NAME = 'trg_order_lifecycle_control_events_before_update'
      AND EVENT_OBJECT_TABLE = 'order_lifecycle_control_events'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'UPDATE'
      AND ACTION_STATEMENT LIKE 'SIGNAL SQLSTATE ''45000''%'
);
SET @olcf_events_delete_trigger_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND TRIGGER_NAME = 'trg_order_lifecycle_control_events_before_delete'
      AND EVENT_OBJECT_TABLE = 'order_lifecycle_control_events'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'DELETE'
      AND ACTION_STATEMENT LIKE 'SIGNAL SQLSTATE ''45000''%'
);
SET @olcf_events_trigger_guard_sql = IF(
    @olcf_events_preexisting = 0
    OR (
        @olcf_events_update_trigger_exact = 1
        AND @olcf_events_delete_trigger_exact = 1
    ),
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_EVENTS_TRIGGER_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_events_trigger_guard_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

DROP TRIGGER IF EXISTS trg_order_lifecycle_control_events_before_update;
CREATE TRIGGER trg_order_lifecycle_control_events_before_update
BEFORE UPDATE ON order_lifecycle_control_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_lifecycle_control_events_before_delete;
CREATE TRIGGER trg_order_lifecycle_control_events_before_delete
BEFORE DELETE ON order_lifecycle_control_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be deleted';

SET @olcf_state_preexisting = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
);

CREATE TABLE IF NOT EXISTS order_lifecycle_control_state (
    case_no VARCHAR(50) NOT NULL,
    control_type ENUM(
        'cancellation',
        'actual_start_reconfirmation',
        'human_hold'
    ) NOT NULL,
    control_key VARCHAR(100) NOT NULL,
    scope ENUM('order', 'enter_service', 'auto_complete') NOT NULL,
    state ENUM('active', 'cleared') NOT NULL,
    current_event_id BIGINT UNSIGNED NOT NULL,
    release_policy ENUM('manual', 'expires_at') NULL,
    expires_at_utc DATETIME(6) NULL,
    confirmed_start_date DATE NULL,
    deposit_settlement_identity_hash CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    reason VARCHAR(500) NOT NULL,
    changed_by VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (case_no, control_type, control_key),
    INDEX idx_order_lifecycle_control_state_case_status_type (
        case_no,
        state,
        control_type
    ),
    CONSTRAINT fk_order_lifecycle_control_state_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_lifecycle_control_state_event
        FOREIGN KEY (
            current_event_id,
            case_no,
            control_type,
            control_key
        )
        REFERENCES order_lifecycle_control_events (
            id,
            case_no,
            control_type,
            control_key
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_control_state_text
        CHECK (
            CHAR_LENGTH(TRIM(control_key)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(changed_by)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_control_state_confirmation_hash
        CHECK (
            deposit_settlement_identity_hash IS NULL
            OR deposit_settlement_identity_hash REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_lifecycle_control_state_shape
        CHECK (
            (
                control_type = 'cancellation'
                AND control_key = 'order_cancelled'
                AND scope = 'order'
                AND release_policy IS NULL
                AND expires_at_utc IS NULL
                AND confirmed_start_date IS NULL
                AND deposit_settlement_identity_hash IS NULL
            )
            OR
            (
                control_type = 'actual_start_reconfirmation'
                AND control_key = 'actual_start_reconfirmation'
                AND scope = 'enter_service'
                AND release_policy IS NULL
                AND expires_at_utc IS NULL
                AND (
                    (
                        state = 'active'
                        AND confirmed_start_date IS NULL
                        AND deposit_settlement_identity_hash IS NULL
                    )
                    OR
                    (
                        state = 'cleared'
                        AND confirmed_start_date IS NOT NULL
                        AND deposit_settlement_identity_hash IS NOT NULL
                    )
                )
            )
            OR
            (
                control_type = 'human_hold'
                AND scope IN ('enter_service', 'auto_complete')
                AND confirmed_start_date IS NULL
                AND deposit_settlement_identity_hash IS NULL
                AND (
                    (
                        release_policy = 'manual'
                        AND expires_at_utc IS NULL
                    )
                    OR
                    (
                        release_policy = 'expires_at'
                        AND expires_at_utc IS NOT NULL
                    )
                )
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @olcf_state_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
);
SET @olcf_state_columns_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
      AND (
          (
              COLUMN_NAME = 'case_no'
              AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_type'
              AND COLUMN_TYPE = 'enum(''cancellation'',''actual_start_reconfirmation'',''human_hold'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'control_key'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'scope'
              AND COLUMN_TYPE = 'enum(''order'',''enter_service'',''auto_complete'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'state'
              AND COLUMN_TYPE = 'enum(''active'',''cleared'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'current_event_id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'release_policy'
              AND COLUMN_TYPE = 'enum(''manual'',''expires_at'')'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME IN ('expires_at_utc')
              AND COLUMN_TYPE = 'datetime(6)'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'confirmed_start_date'
              AND DATA_TYPE = 'date'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'deposit_settlement_identity_hash'
              AND COLUMN_TYPE = 'char(64)'
              AND IS_NULLABLE = 'YES'
              AND CHARACTER_SET_NAME = 'ascii'
              AND COLLATION_NAME = 'ascii_bin'
          )
          OR
          (
              COLUMN_NAME = 'reason'
              AND COLUMN_TYPE = 'varchar(500)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'changed_by'
              AND COLUMN_TYPE = 'varchar(100)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'changed_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
          )
      )
);
SET @olcf_state_index_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
      AND (
          (
              INDEX_NAME = 'PRIMARY'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_key')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_control_state_case_status_type'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'state')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_type')
              )
          )
          OR
          (
              INDEX_NAME = 'fk_order_lifecycle_control_state_event'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'current_event_id')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'control_type')
                  OR
                  (SEQ_IN_INDEX = 4 AND COLUMN_NAME = 'control_key')
              )
          )
      )
);
SET @olcf_state_case_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_control_state'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_control_state_case'
      AND k.COLUMN_NAME = 'case_no'
      AND k.REFERENCED_TABLE_NAME = 'orders'
      AND k.REFERENCED_COLUMN_NAME = 'case_no'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_state_event_fk_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_control_state'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_control_state_event'
      AND k.REFERENCED_TABLE_NAME = 'order_lifecycle_control_events'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
      AND (
          (
              k.ORDINAL_POSITION = 1
              AND k.COLUMN_NAME = 'current_event_id'
              AND k.REFERENCED_COLUMN_NAME = 'id'
          )
          OR
          (
              k.ORDINAL_POSITION = 2
              AND k.COLUMN_NAME = 'case_no'
              AND k.REFERENCED_COLUMN_NAME = 'case_no'
          )
          OR
          (
              k.ORDINAL_POSITION = 3
              AND k.COLUMN_NAME = 'control_type'
              AND k.REFERENCED_COLUMN_NAME = 'control_type'
          )
          OR
          (
              k.ORDINAL_POSITION = 4
              AND k.COLUMN_NAME = 'control_key'
              AND k.REFERENCED_COLUMN_NAME = 'control_key'
          )
      )
);
SET @olcf_state_checks_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'order_lifecycle_control_state'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_state_text'
              AND cc.CHECK_CLAUSE LIKE '%control_key%'
              AND cc.CHECK_CLAUSE LIKE '%changed_by%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_state_confirmation_hash'
              AND cc.CHECK_CLAUSE LIKE '%deposit_settlement_identity_hash%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_control_state_shape'
              AND cc.CHECK_CLAUSE LIKE '%confirmed_start_date%'
              AND cc.CHECK_CLAUSE LIKE '%expires_at_utc%'
              AND cc.CHECK_CLAUSE LIKE '%release_policy%'
          )
      )
);
SET @olcf_state_table_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_control_state'
      AND ENGINE = 'InnoDB'
      AND TABLE_COLLATION = 'utf8mb4_unicode_ci'
);
SET @olcf_state_metadata_sql = IF(
    @olcf_state_column_count = 13
    AND @olcf_state_columns_exact = 13
    AND @olcf_state_index_parts_exact = 10
    AND @olcf_state_case_fk_exact = 1
    AND @olcf_state_event_fk_parts_exact = 4
    AND @olcf_state_checks_exact = 3
    AND @olcf_state_table_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_STATE_METADATA_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_state_metadata_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

SET @olcf_state_delete_trigger_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
      AND TRIGGER_NAME = 'trg_order_lifecycle_control_state_before_delete'
      AND EVENT_OBJECT_TABLE = 'order_lifecycle_control_state'
      AND ACTION_TIMING = 'BEFORE'
      AND EVENT_MANIPULATION = 'DELETE'
      AND ACTION_STATEMENT LIKE 'SIGNAL SQLSTATE ''45000''%'
);
SET @olcf_state_trigger_guard_sql = IF(
    @olcf_state_preexisting = 0
    OR @olcf_state_delete_trigger_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_CONTROL_STATE_TRIGGER_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_state_trigger_guard_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

DROP TRIGGER IF EXISTS trg_order_lifecycle_control_state_before_delete;
CREATE TRIGGER trg_order_lifecycle_control_state_before_delete
BEFORE DELETE ON order_lifecycle_control_state
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_state records cannot be deleted';

CREATE TABLE IF NOT EXISTS order_lifecycle_projection_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    scope ENUM('enter_service', 'auto_complete') NOT NULL,
    alert_code VARCHAR(191) NOT NULL,
    action ENUM('open', 'resolve') NOT NULL,
    payload_hash CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM(
        'pending',
        'processing',
        'projected',
        'failed'
    ) NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME(6) NULL,
    locked_at_utc DATETIME(6) NULL,
    projected_at_utc DATETIME(6) NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_lifecycle_projection_outbox_intent (
        case_no,
        intent_key
    ),
    INDEX idx_order_lifecycle_projection_outbox_retry (
        status,
        next_attempt_at_utc,
        id
    ),
    INDEX idx_order_lifecycle_projection_outbox_event (
        case_no,
        lifecycle_event_id
    ),
    CONSTRAINT fk_order_lifecycle_projection_outbox_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_lifecycle_projection_outbox_event
        FOREIGN KEY (lifecycle_event_id)
        REFERENCES order_lifecycle_state_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_projection_outbox_text
        CHECK (
            CHAR_LENGTH(TRIM(intent_key)) > 0
            AND CHAR_LENGTH(TRIM(alert_code)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_projection_outbox_payload
        CHECK (
            payload_hash REGEXP '^[0-9a-f]{64}$'
            AND JSON_TYPE(payload_snapshot) = 'OBJECT'
        ),
    CONSTRAINT chk_order_lifecycle_projection_outbox_status
        CHECK (
            (
                status = 'pending'
                AND locked_at_utc IS NULL
                AND projected_at_utc IS NULL
                AND last_error IS NULL
            )
            OR
            (
                status = 'processing'
                AND locked_at_utc IS NOT NULL
                AND projected_at_utc IS NULL
            )
            OR
            (
                status = 'projected'
                AND projected_at_utc IS NOT NULL
                AND last_error IS NULL
            )
            OR
            (
                status = 'failed'
                AND projected_at_utc IS NULL
                AND last_error IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @olcf_outbox_column_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
);
SET @olcf_outbox_columns_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND (
          (
              COLUMN_NAME = 'id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
              AND EXTRA = 'auto_increment'
          )
          OR
          (
              COLUMN_NAME = 'case_no'
              AND COLUMN_TYPE = 'varchar(50)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'lifecycle_event_id'
              AND COLUMN_TYPE = 'bigint unsigned'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'intent_key'
              AND COLUMN_TYPE = 'varchar(191)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'scope'
              AND COLUMN_TYPE = 'enum(''enter_service'',''auto_complete'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'alert_code'
              AND COLUMN_TYPE = 'varchar(191)'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'action'
              AND COLUMN_TYPE = 'enum(''open'',''resolve'')'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'payload_hash'
              AND COLUMN_TYPE = 'char(64)'
              AND IS_NULLABLE = 'NO'
              AND CHARACTER_SET_NAME = 'ascii'
              AND COLLATION_NAME = 'ascii_bin'
          )
          OR
          (
              COLUMN_NAME = 'payload_snapshot'
              AND DATA_TYPE = 'json'
              AND IS_NULLABLE = 'NO'
          )
          OR
          (
              COLUMN_NAME = 'status'
              AND COLUMN_TYPE = 'enum(''pending'',''processing'',''projected'',''failed'')'
              AND IS_NULLABLE = 'NO'
              AND COLUMN_DEFAULT = 'pending'
          )
          OR
          (
              COLUMN_NAME = 'attempt_count'
              AND COLUMN_TYPE = 'int unsigned'
              AND IS_NULLABLE = 'NO'
              AND COLUMN_DEFAULT = '0'
          )
          OR
          (
              COLUMN_NAME IN (
                  'next_attempt_at_utc',
                  'locked_at_utc',
                  'projected_at_utc'
              )
              AND COLUMN_TYPE = 'datetime(6)'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'last_error'
              AND COLUMN_TYPE = 'varchar(1000)'
              AND IS_NULLABLE = 'YES'
          )
          OR
          (
              COLUMN_NAME = 'created_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
              AND EXTRA NOT LIKE '%on update%'
          )
          OR
          (
              COLUMN_NAME = 'updated_at'
              AND COLUMN_TYPE = 'timestamp(6)'
              AND IS_NULLABLE = 'NO'
              AND LOWER(COLUMN_DEFAULT) = 'current_timestamp(6)'
              AND EXTRA = 'DEFAULT_GENERATED on update CURRENT_TIMESTAMP(6)'
          )
      )
);
SET @olcf_outbox_index_parts_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND (
          (
              INDEX_NAME = 'PRIMARY'
              AND NON_UNIQUE = 0
              AND SEQ_IN_INDEX = 1
              AND COLUMN_NAME = 'id'
          )
          OR
          (
              INDEX_NAME = 'uq_order_lifecycle_projection_outbox_intent'
              AND NON_UNIQUE = 0
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'intent_key')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_projection_outbox_retry'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'status')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'next_attempt_at_utc')
                  OR
                  (SEQ_IN_INDEX = 3 AND COLUMN_NAME = 'id')
              )
          )
          OR
          (
              INDEX_NAME = 'idx_order_lifecycle_projection_outbox_event'
              AND NON_UNIQUE = 1
              AND (
                  (SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'case_no')
                  OR
                  (SEQ_IN_INDEX = 2 AND COLUMN_NAME = 'lifecycle_event_id')
              )
          )
          OR
          (
              INDEX_NAME = 'fk_order_lifecycle_projection_outbox_event'
              AND NON_UNIQUE = 1
              AND SEQ_IN_INDEX = 1
              AND COLUMN_NAME = 'lifecycle_event_id'
          )
      )
);
SET @olcf_outbox_case_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_projection_outbox_case'
      AND k.COLUMN_NAME = 'case_no'
      AND k.REFERENCED_TABLE_NAME = 'orders'
      AND k.REFERENCED_COLUMN_NAME = 'case_no'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_outbox_event_fk_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
    JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
     AND r.TABLE_NAME = k.TABLE_NAME
     AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA = DATABASE()
      AND k.TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND k.CONSTRAINT_NAME = 'fk_order_lifecycle_projection_outbox_event'
      AND k.COLUMN_NAME = 'lifecycle_event_id'
      AND k.REFERENCED_TABLE_NAME = 'order_lifecycle_state_events'
      AND k.REFERENCED_COLUMN_NAME = 'id'
      AND r.UPDATE_RULE = 'RESTRICT'
      AND r.DELETE_RULE = 'RESTRICT'
);
SET @olcf_outbox_checks_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
      ON cc.CONSTRAINT_CATALOG = tc.CONSTRAINT_CATALOG
     AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
      AND tc.TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND tc.CONSTRAINT_TYPE = 'CHECK'
      AND tc.ENFORCED = 'YES'
      AND (
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_projection_outbox_text'
              AND cc.CHECK_CLAUSE LIKE '%intent_key%'
              AND cc.CHECK_CLAUSE LIKE '%alert_code%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_projection_outbox_payload'
              AND cc.CHECK_CLAUSE LIKE '%payload_hash%'
              AND cc.CHECK_CLAUSE LIKE '%payload_snapshot%'
          )
          OR
          (
              tc.CONSTRAINT_NAME = 'chk_order_lifecycle_projection_outbox_status'
              AND cc.CHECK_CLAUSE LIKE '%processing%'
              AND cc.CHECK_CLAUSE LIKE '%projected_at_utc%'
              AND cc.CHECK_CLAUSE LIKE '%last_error%'
          )
      )
);
SET @olcf_outbox_table_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_lifecycle_projection_outbox'
      AND ENGINE = 'InnoDB'
      AND TABLE_COLLATION = 'utf8mb4_unicode_ci'
);
SET @olcf_outbox_metadata_sql = IF(
    @olcf_outbox_column_count = 17
    AND @olcf_outbox_columns_exact = 17
    AND @olcf_outbox_index_parts_exact = 9
    AND @olcf_outbox_case_fk_exact = 1
    AND @olcf_outbox_event_fk_exact = 1
    AND @olcf_outbox_checks_exact = 3
    AND @olcf_outbox_table_exact = 1,
    'SELECT 1',
    'SELECT * FROM `FAIL_CLOSED_ORDER_LIFECYCLE_PROJECTION_OUTBOX_METADATA_DRIFT`'
);
PREPARE olcf_stmt FROM @olcf_outbox_metadata_sql;
EXECUTE olcf_stmt;
DEALLOCATE PREPARE olcf_stmt;

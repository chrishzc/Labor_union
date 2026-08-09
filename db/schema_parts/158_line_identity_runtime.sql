-- Canonical LINE platform friend state, LIFF identity flow, and review creation facts.
-- Additive Stage 4 migration; legacy projections remain available until Stage 10.

CREATE TABLE IF NOT EXISTS line_platform_users (
    line_user_id VARCHAR(191) PRIMARY KEY,
    friend_status ENUM('unknown','active','blocked') NOT NULL DEFAULT 'unknown',
    first_followed_at_utc DATETIME(6) NULL,
    last_followed_at_utc DATETIME(6) NULL,
    blocked_at_utc DATETIME(6) NULL,
    last_event_at_utc DATETIME(6) NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_platform_friend_state (friend_status, last_event_at_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_platform_users (
    line_user_id, friend_status, first_followed_at_utc, last_followed_at_utc,
    blocked_at_utc, last_event_at_utc, aggregate_version, created_at_utc, updated_at_utc
)
SELECT
    line_user_id,
    CASE status WHEN 'active' THEN 'active' WHEN 'blocked' THEN 'blocked' ELSE 'unknown' END,
    followed_at,
    followed_at,
    blocked_at,
    last_event_at,
    0,
    created_at,
    updated_at
FROM line_users;

CREATE TABLE IF NOT EXISTS line_friend_state_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    event_type ENUM('follow','unfollow','activity') NOT NULL,
    before_status ENUM('unknown','active','blocked') NOT NULL,
    after_status ENUM('active','blocked') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_friend_event_identity (event_identity),
    INDEX idx_line_friend_event_user (line_user_id, id),
    CONSTRAINT fk_line_friend_event_user FOREIGN KEY (line_user_id)
        REFERENCES line_platform_users(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_friend_event_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_flows (
    flow_id CHAR(36) PRIMARY KEY,
    flow_purpose ENUM('customer_binding','staff_verification','admin_binding') NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    flow_status ENUM('active','used','expired','cancelled') NOT NULL DEFAULT 'active',
    expires_at_utc DATETIME(6) NOT NULL,
    used_at_utc DATETIME(6) NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_flow_idempotency (idempotency_key),
    INDEX idx_line_identity_flow_user (line_user_id, flow_status, expires_at_utc),
    CONSTRAINT fk_line_identity_flow_user FOREIGN KEY (line_user_id)
        REFERENCES line_platform_users(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- MySQL versions used by this project do not consistently support conditional
-- column-add syntax. Use metadata-gated DDL so this release is replayable.
SET @line_review_flow_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND COLUMN_NAME='identity_flow_id'
);
SET @line_review_flow_column_sql := IF(
    @line_review_flow_column_exists=0,
    'ALTER TABLE line_review_requests ADD COLUMN identity_flow_id CHAR(36) NULL AFTER evidence_snapshot',
    'SELECT 1'
);
PREPARE line_review_flow_column_stmt FROM @line_review_flow_column_sql;
EXECUTE line_review_flow_column_stmt;
DEALLOCATE PREPARE line_review_flow_column_stmt;

SET @line_review_request_key_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND COLUMN_NAME='request_idempotency_key'
);
SET @line_review_request_key_column_sql := IF(
    @line_review_request_key_column_exists=0,
    'ALTER TABLE line_review_requests ADD COLUMN request_idempotency_key VARCHAR(191) NULL AFTER identity_flow_id',
    'SELECT 1'
);
PREPARE line_review_request_key_column_stmt FROM @line_review_request_key_column_sql;
EXECUTE line_review_request_key_column_stmt;
DEALLOCATE PREPARE line_review_request_key_column_stmt;

SET @line_review_correlation_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND COLUMN_NAME='request_correlation_id'
);
SET @line_review_correlation_column_sql := IF(
    @line_review_correlation_column_exists=0,
    'ALTER TABLE line_review_requests ADD COLUMN request_correlation_id VARCHAR(191) NULL AFTER request_idempotency_key',
    'SELECT 1'
);
PREPARE line_review_correlation_column_stmt FROM @line_review_correlation_column_sql;
EXECUTE line_review_correlation_column_stmt;
DEALLOCATE PREPARE line_review_correlation_column_stmt;

SET @line_review_flow_index_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND INDEX_NAME='uq_line_review_identity_flow'
);
SET @line_review_flow_index_sql := IF(
    @line_review_flow_index_exists=0,
    'ALTER TABLE line_review_requests ADD UNIQUE KEY uq_line_review_identity_flow (identity_flow_id)',
    'SELECT 1'
);
PREPARE line_review_flow_index_stmt FROM @line_review_flow_index_sql;
EXECUTE line_review_flow_index_stmt;
DEALLOCATE PREPARE line_review_flow_index_stmt;

SET @line_review_request_key_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND INDEX_NAME='uq_line_review_request_idempotency'
);
SET @line_review_request_key_sql := IF(
    @line_review_request_key_exists=0,
    'ALTER TABLE line_review_requests ADD UNIQUE KEY uq_line_review_request_idempotency (request_idempotency_key)',
    'SELECT 1'
);
PREPARE line_review_request_key_stmt FROM @line_review_request_key_sql;
EXECUTE line_review_request_key_stmt;
DEALLOCATE PREPARE line_review_request_key_stmt;

SET @line_review_flow_fk_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='line_review_requests'
      AND CONSTRAINT_NAME='fk_line_review_identity_flow'
);
SET @line_review_flow_fk_sql := IF(
    @line_review_flow_fk_exists=0,
    'ALTER TABLE line_review_requests ADD CONSTRAINT fk_line_review_identity_flow FOREIGN KEY (identity_flow_id) REFERENCES line_identity_flows(flow_id) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE line_review_flow_fk_stmt FROM @line_review_flow_fk_sql;
EXECUTE line_review_flow_fk_stmt;
DEALLOCATE PREPARE line_review_flow_fk_stmt;

SET @line_identity_subject_index_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_identity_bindings'
      AND INDEX_NAME='uq_line_identity_subject'
);
SET @line_identity_subject_drop_sql := IF(
    @line_identity_subject_index_exists>0,
    'ALTER TABLE line_identity_bindings DROP INDEX uq_line_identity_subject',
    'SELECT 1'
);
PREPARE line_identity_subject_drop_stmt FROM @line_identity_subject_drop_sql;
EXECUTE line_identity_subject_drop_stmt;
DEALLOCATE PREPARE line_identity_subject_drop_stmt;

SET @line_identity_active_subject_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_identity_bindings'
      AND COLUMN_NAME='active_subject_key'
);
SET @line_identity_active_subject_column_sql := IF(
    @line_identity_active_subject_column_exists=0,
    'ALTER TABLE line_identity_bindings ADD COLUMN active_subject_key VARCHAR(400) GENERATED ALWAYS AS (CASE WHEN binding_status IN (''pending_review'',''bound'') THEN CONCAT(subject_type, '':'', subject_reference) ELSE NULL END) STORED',
    'SELECT 1'
);
PREPARE line_identity_active_subject_column_stmt
    FROM @line_identity_active_subject_column_sql;
EXECUTE line_identity_active_subject_column_stmt;
DEALLOCATE PREPARE line_identity_active_subject_column_stmt;

SET @line_identity_active_subject_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_identity_bindings'
      AND INDEX_NAME='uq_line_identity_active_subject'
);
SET @line_identity_active_subject_sql := IF(
    @line_identity_active_subject_exists=0,
    'ALTER TABLE line_identity_bindings ADD UNIQUE KEY uq_line_identity_active_subject (active_subject_key)',
    'SELECT 1'
);
PREPARE line_identity_active_subject_stmt FROM @line_identity_active_subject_sql;
EXECUTE line_identity_active_subject_stmt;
DEALLOCATE PREPARE line_identity_active_subject_stmt;

DROP TRIGGER IF EXISTS trg_line_friend_state_events_before_update;
CREATE TRIGGER trg_line_friend_state_events_before_update
BEFORE UPDATE ON line_friend_state_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_friend_state_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_friend_state_events_before_delete;
CREATE TRIGGER trg_line_friend_state_events_before_delete
BEFORE DELETE ON line_friend_state_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_friend_state_events records cannot be deleted';

-- File: 1019_line_identity_role_scope.sql
-- Description: Shared role-scoped LINE identity roots and bounded failure streak.
-- Additive successor only; legacy roots/events remain compatibility read surfaces.

-- Replaying this released part after a later statement fails must not collide
-- with the already-added parent column. Incompatible pre-existing shapes fail
-- closed instead of being silently rewritten.
SET @line_selected_role_column_any = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_platform_users'
      AND COLUMN_NAME = 'selected_identity_role'
);
SET @line_selected_role_column_exact = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'line_platform_users'
      AND COLUMN_NAME = 'selected_identity_role'
      AND DATA_TYPE = 'enum'
      AND COLUMN_TYPE = 'enum(''customer'',''staff'')'
      AND IS_NULLABLE = 'YES'
      AND COLUMN_DEFAULT IS NULL
      AND EXTRA = ''
      AND COALESCE(GENERATION_EXPRESSION, '') = ''
);
SET @line_selected_role_column_sql = IF(
    @line_selected_role_column_any = 0,
    'ALTER TABLE line_platform_users ADD COLUMN selected_identity_role ENUM(''customer'',''staff'') NULL AFTER aggregate_version',
    IF(
        @line_selected_role_column_any = 1
        AND @line_selected_role_column_exact = 1,
        'SELECT 1',
        'SELECT * FROM `FAIL_CLOSED_LINE_SELECTED_ROLE_INVALID_SPEC`'
    )
);
PREPARE line_selected_role_column_stmt FROM @line_selected_role_column_sql;
EXECUTE line_selected_role_column_stmt;
DEALLOCATE PREPARE line_selected_role_column_stmt;

CREATE TABLE IF NOT EXISTS line_identity_role_bindings (
    line_user_id VARCHAR(191) NOT NULL,
    subject_type ENUM('customer','staff','admin') NOT NULL,
    binding_status ENUM(
        'pending_review','bound','revocation_pending','revoked'
    ) NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    active_subject_key VARCHAR(400) GENERATED ALWAYS AS (
        CASE
            WHEN binding_status IN ('pending_review','bound','revocation_pending')
            THEN CONCAT(subject_type, ':', subject_reference)
            ELSE NULL
        END
    ) STORED,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (line_user_id, subject_type),
    UNIQUE KEY uq_line_identity_role_active_subject (active_subject_key),
    INDEX idx_line_identity_role_status (
        subject_type, binding_status, updated_at_utc, line_user_id
    ),
    CONSTRAINT fk_line_identity_role_platform_user
        FOREIGN KEY (line_user_id) REFERENCES line_platform_users(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_role_subject_reference
        CHECK (CHAR_LENGTH(TRIM(subject_reference)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_role_binding_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    subject_type ENUM('customer','staff','admin') NOT NULL,
    action ENUM(
        'claim_submitted','bound','revocation_requested','revoked','rebound',
        'legacy_imported'
    ) NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_role_event_idempotency (idempotency_key),
    INDEX idx_line_identity_role_event_stream (
        line_user_id, subject_type, id
    ),
    CONSTRAINT fk_line_identity_role_event_binding
        FOREIGN KEY (line_user_id, subject_type)
        REFERENCES line_identity_role_bindings(line_user_id, subject_type)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_role_event_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_identity_role_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_line_identity_role_event_text
        CHECK (
            CHAR_LENGTH(TRIM(subject_reference)) > 0
            AND CHAR_LENGTH(TRIM(actor_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_binding_failure_streaks (
    line_user_id VARCHAR(191) PRIMARY KEY,
    identity_flow_id CHAR(36) NOT NULL,
    candidate_subject_type ENUM('customer','staff') NOT NULL,
    candidate_scope VARCHAR(191) NOT NULL,
    scope_fingerprint CHAR(64) NOT NULL,
    streak_generation BIGINT UNSIGNED NOT NULL DEFAULT 0,
    failure_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
    last_failure_fingerprint CHAR(64) NULL,
    escalation_id BIGINT UNSIGNED NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_identity_failure_flow (
        identity_flow_id, candidate_subject_type, candidate_scope
    ),
    INDEX idx_line_identity_failure_escalation (escalation_id),
    CONSTRAINT fk_line_identity_failure_platform_user
        FOREIGN KEY (line_user_id) REFERENCES line_platform_users(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_identity_failure_flow
        FOREIGN KEY (identity_flow_id) REFERENCES line_identity_flows(flow_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_identity_failure_escalation
        FOREIGN KEY (escalation_id) REFERENCES customer_service_escalations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_failure_scope
        CHECK (
            scope_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND CHAR_LENGTH(TRIM(candidate_scope)) > 0
        ),
    CONSTRAINT chk_line_identity_failure_count
        CHECK (failure_count BETWEEN 0 AND 2),
    CONSTRAINT chk_line_identity_failure_shape
        CHECK (
            (failure_count = 0
             AND last_failure_fingerprint IS NULL
             AND escalation_id IS NULL)
            OR
            (failure_count = 1
             AND last_failure_fingerprint REGEXP '^[0-9a-f]{64}$'
             AND escalation_id IS NULL)
            OR
            (failure_count = 2
             AND last_failure_fingerprint REGEXP '^[0-9a-f]{64}$'
             AND escalation_id IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_identity_role_bindings (
    line_user_id, subject_type, binding_status, subject_reference,
    aggregate_version, created_at_utc, updated_at_utc
)
SELECT
    legacy.line_user_id,
    legacy.subject_type,
    legacy.binding_status,
    legacy.subject_reference,
    legacy.aggregate_version,
    legacy.created_at_utc,
    legacy.updated_at_utc
FROM line_identity_bindings AS legacy
INNER JOIN line_platform_users AS platform_user
    ON platform_user.line_user_id = legacy.line_user_id
WHERE legacy.subject_type IS NOT NULL
  AND legacy.subject_reference IS NOT NULL
  AND legacy.binding_status <> 'unbound';

INSERT IGNORE INTO line_identity_role_binding_events (
    id, line_user_id, subject_type, action, subject_reference,
    expected_version, resulting_version, actor_id, payload_fingerprint,
    idempotency_key, correlation_id, occurred_at_utc
)
SELECT
    legacy_event.id,
    legacy_event.line_user_id,
    legacy_event.subject_type,
    legacy_event.action,
    legacy_event.subject_reference,
    legacy_event.expected_version,
    legacy_event.resulting_version,
    legacy_event.actor_id,
    legacy_event.payload_fingerprint,
    legacy_event.idempotency_key,
    legacy_event.correlation_id,
    legacy_event.occurred_at_utc
FROM line_identity_binding_events AS legacy_event
INNER JOIN line_identity_role_bindings AS role_binding
    ON role_binding.line_user_id = legacy_event.line_user_id
   AND role_binding.subject_type = legacy_event.subject_type
WHERE legacy_event.subject_type IS NOT NULL
  AND legacy_event.subject_reference IS NOT NULL;

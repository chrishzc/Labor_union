-- Canonical LINE identity bindings, review facts, and versioned configuration.

CREATE TABLE IF NOT EXISTS line_identity_bindings (
    line_user_id VARCHAR(191) PRIMARY KEY,
    binding_status ENUM('unbound','pending_review','bound','revoked')
        NOT NULL DEFAULT 'unbound',
    subject_type ENUM('customer','staff','admin') NULL,
    subject_reference VARCHAR(191) NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_subject (subject_type, subject_reference),
    INDEX idx_line_identity_status (binding_status, updated_at_utc),
    CONSTRAINT chk_line_identity_subject_pair CHECK (
        (binding_status = 'unbound' AND subject_type IS NULL AND subject_reference IS NULL)
        OR
        (binding_status <> 'unbound' AND subject_type IS NOT NULL
            AND subject_reference IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_binding_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    action ENUM('claim_submitted','bound','revoked','rebound','legacy_imported')
        NOT NULL,
    subject_type ENUM('customer','staff','admin') NULL,
    subject_reference VARCHAR(191) NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_event_idempotency (idempotency_key),
    INDEX idx_line_identity_event_user (line_user_id, id),
    CONSTRAINT fk_line_identity_event_binding
        FOREIGN KEY (line_user_id) REFERENCES line_identity_bindings(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_event_fingerprint
        CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_identity_event_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_identity_migration_anomalies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    candidate_count INT UNSIGNED NOT NULL,
    candidate_snapshot JSON NOT NULL,
    detected_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_identity_migration_anomaly (line_user_id),
    CONSTRAINT chk_line_identity_anomaly_snapshot
        CHECK (JSON_TYPE(candidate_snapshot) = 'ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_identity_bindings (
    line_user_id, binding_status, subject_type, subject_reference,
    aggregate_version, created_at_utc, updated_at_utc
)
SELECT
    candidate.line_user_id,
    'bound',
    MIN(candidate.subject_type),
    MIN(candidate.subject_reference),
    1,
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
FROM (
    SELECT line_user_id, 'customer' AS subject_type, CAST(id AS CHAR) AS subject_reference
    FROM clients WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT line_user_id, 'staff', CAST(id AS CHAR)
    FROM staff WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT linked_line_user_id, 'admin', CAST(id AS CHAR)
    FROM admin_users
    WHERE linked_line_user_id IS NOT NULL AND linked_line_user_id <> ''
) AS candidate
GROUP BY candidate.line_user_id
HAVING COUNT(*) = 1;

INSERT IGNORE INTO line_identity_bindings (
    line_user_id, binding_status, aggregate_version, created_at_utc, updated_at_utc
)
SELECT line_user_id, 'unbound', 0, created_at, updated_at
FROM line_users;

INSERT IGNORE INTO line_identity_migration_anomalies (
    line_user_id, candidate_count, candidate_snapshot
)
SELECT
    candidate.line_user_id,
    COUNT(*),
    JSON_ARRAYAGG(JSON_OBJECT(
        'subject_reference', candidate.subject_reference,
        'subject_type', candidate.subject_type
    ))
FROM (
    SELECT line_user_id, 'customer' AS subject_type, CAST(id AS CHAR) AS subject_reference
    FROM clients WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT line_user_id, 'staff', CAST(id AS CHAR)
    FROM staff WHERE line_user_id IS NOT NULL AND line_user_id <> ''
    UNION ALL
    SELECT linked_line_user_id, 'admin', CAST(id AS CHAR)
    FROM admin_users
    WHERE linked_line_user_id IS NOT NULL AND linked_line_user_id <> ''
) AS candidate
GROUP BY candidate.line_user_id
HAVING COUNT(*) > 1;

INSERT IGNORE INTO line_identity_binding_events (
    line_user_id, action, subject_type, subject_reference,
    expected_version, resulting_version, actor_id, payload_fingerprint,
    idempotency_key, correlation_id
)
SELECT
    line_user_id,
    'legacy_imported',
    subject_type,
    subject_reference,
    0,
    1,
    'migration:line-stage-2',
    SHA2(CONCAT_WS('|', line_user_id, subject_type, subject_reference), 256),
    CONCAT('legacy-line-binding:', line_user_id),
    CONCAT('legacy-line-binding:', line_user_id)
FROM line_identity_bindings
WHERE binding_status = 'bound';

CREATE TABLE IF NOT EXISTS line_review_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    review_type ENUM('client_rebind','staff_verification','admin_binding') NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    subject_type ENUM('customer','staff','admin') NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    review_status ENUM('pending','approved','rejected','cancelled','expired')
        NOT NULL DEFAULT 'pending',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    request_fingerprint CHAR(64) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    assigned_admin_id BIGINT NULL,
    assigned_at_utc DATETIME(6) NULL,
    due_at_utc DATETIME(6) NULL,
    reassignment_count INT UNSIGNED NOT NULL DEFAULT 0,
    reviewed_by_actor_id VARCHAR(191) NULL,
    decision_reason VARCHAR(1000) NULL,
    reviewed_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_line_review_queue (review_status, review_type, created_at_utc, id),
    INDEX idx_line_review_assignee (assigned_admin_id, review_status, due_at_utc),
    CONSTRAINT fk_line_review_assignee
        FOREIGN KEY (assigned_admin_id) REFERENCES admin_users(id)
        ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT chk_line_review_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_review_evidence
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_review_requests (
    id, review_type, line_user_id, subject_type, subject_reference,
    review_status, aggregate_version, request_fingerprint, evidence_snapshot,
    assigned_admin_id, reviewed_by_actor_id, decision_reason, reviewed_at_utc,
    created_at_utc, updated_at_utc
)
SELECT
    id,
    request_type,
    line_user_id,
    CASE request_type WHEN 'staff_verification' THEN 'staff' ELSE 'customer' END,
    COALESCE(CAST(client_id AS CHAR), client_name, line_user_id),
    status,
    CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
    SHA2(CONCAT_WS('|', request_type, line_user_id, COALESCE(client_id, ''),
        COALESCE(old_line_user_id, ''), COALESCE(new_line_user_id, '')), 256),
    JSON_OBJECT(
        'client_id', client_id,
        'client_name', client_name,
        'new_line_user_id', new_line_user_id,
        'old_line_user_id', old_line_user_id
    ),
    reviewed_by_admin_user_id,
    COALESCE(CAST(reviewed_by_admin_user_id AS CHAR), reviewed_by_line_user_id),
    decision_reason,
    COALESCE(reviewed_at, resolved_at),
    created_at,
    updated_at
FROM line_confirmation_requests;

CREATE TABLE IF NOT EXISTS line_review_decision_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    review_request_id BIGINT UNSIGNED NOT NULL,
    before_status ENUM('pending','approved','rejected','cancelled','expired') NOT NULL,
    after_status ENUM('approved','rejected','cancelled','expired') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    decision_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_review_decision_idempotency (idempotency_key),
    INDEX idx_line_review_decision_request (review_request_id, id),
    CONSTRAINT fk_line_review_decision_request
        FOREIGN KEY (review_request_id) REFERENCES line_review_requests(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_review_decision_fingerprint
        CHECK (decision_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_review_decision_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_review_decision_events (
    review_request_id, before_status, after_status, expected_version,
    resulting_version, actor_id, reason, decision_fingerprint,
    idempotency_key, correlation_id, occurred_at_utc
)
SELECT
    id,
    'pending',
    status,
    0,
    1,
    COALESCE(CAST(reviewed_by_admin_user_id AS CHAR), reviewed_by_line_user_id,
        'migration:line-stage-2'),
    COALESCE(decision_reason, 'legacy decision import'),
    SHA2(CONCAT_WS('|', id, status, COALESCE(decision_reason, '')), 256),
    CONCAT('legacy-line-review-decision:', id),
    CONCAT('legacy-line-review-decision:', id),
    COALESCE(reviewed_at, resolved_at, updated_at)
FROM line_confirmation_requests
WHERE status IN ('approved','rejected','cancelled');

CREATE TABLE IF NOT EXISTS line_configuration_revisions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service'
    ) NOT NULL,
    revision BIGINT UNSIGNED NOT NULL,
    definition_snapshot JSON NOT NULL,
    definition_fingerprint CHAR(64) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_configuration_revision (configuration_kind, revision),
    UNIQUE KEY uq_line_configuration_idempotency (idempotency_key),
    CONSTRAINT chk_line_configuration_snapshot
        CHECK (JSON_TYPE(definition_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_configuration_fingerprint
        CHECK (definition_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_configuration_current (
    configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service'
    ) PRIMARY KEY,
    revision BIGINT UNSIGNED NOT NULL,
    revision_id BIGINT UNSIGNED NOT NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_configuration_current_revision (revision_id),
    CONSTRAINT fk_line_configuration_current_revision
        FOREIGN KEY (revision_id) REFERENCES line_configuration_revisions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_identity_binding_events_before_update;
CREATE TRIGGER trg_line_identity_binding_events_before_update
BEFORE UPDATE ON line_identity_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_identity_binding_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_identity_binding_events_before_delete;
CREATE TRIGGER trg_line_identity_binding_events_before_delete
BEFORE DELETE ON line_identity_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_identity_binding_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_review_decision_events_before_update;
CREATE TRIGGER trg_line_review_decision_events_before_update
BEFORE UPDATE ON line_review_decision_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_review_decision_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_review_decision_events_before_delete;
CREATE TRIGGER trg_line_review_decision_events_before_delete
BEFORE DELETE ON line_review_decision_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_review_decision_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_configuration_revisions_before_update;
CREATE TRIGGER trg_line_configuration_revisions_before_update
BEFORE UPDATE ON line_configuration_revisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_configuration_revisions records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_configuration_revisions_before_delete;
CREATE TRIGGER trg_line_configuration_revisions_before_delete
BEFORE DELETE ON line_configuration_revisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_configuration_revisions records cannot be deleted';

-- File: 1003_matching_coordination_successor.sql
-- Description: 保存 M3 不可變條件、方案血緣、事件、收據與 typed outbox。

-- Additive M3 persistence only.  These tables do not copy or write any
-- Orders, Assignment, Leave, Scheduling, Payroll, or LINE provider root.
CREATE TABLE IF NOT EXISTS matching_coordination_criteria_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    snapshot_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    criteria_version BIGINT UNSIGNED NOT NULL,
    criteria_snapshot JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    criteria_digest CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_criteria_snapshot_id (snapshot_id),
    UNIQUE KEY uq_matching_criteria_case_version (case_no, criteria_version),
    INDEX idx_matching_criteria_case_time (case_no, created_at_utc),
    CONSTRAINT chk_matching_criteria_identity CHECK (
        CHAR_LENGTH(TRIM(snapshot_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
    ),
    CONSTRAINT chk_matching_criteria_payload CHECK (
        JSON_TYPE(criteria_snapshot) = 'OBJECT' AND JSON_LENGTH(criteria_snapshot) > 0
    ),
    CONSTRAINT chk_matching_criteria_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_criteria_digest CHECK (criteria_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_matching_criteria_actor CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_package_lineage (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    package_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    criteria_snapshot_id BIGINT UNSIGNED NOT NULL,
    parent_package_id BIGINT UNSIGNED NULL,
    package_version BIGINT UNSIGNED NOT NULL,
    lineage_kind ENUM('initial','criteria_diff','rematch','alternative') NOT NULL,
    package_state ENUM(
        'candidate_pool_open','proposed','awaiting_caregiver_willingness',
        'awaiting_customer_decision','no_candidate','alternative_previewed',
        'alternative_applied','no_candidate_terminal','accepted','declined',
        'expired','rematch_required','superseded'
    ) NOT NULL,
    package_snapshot JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    package_digest CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_package_id (package_id),
    UNIQUE KEY uq_matching_package_case_version (case_no, package_version),
    INDEX idx_matching_package_criteria (criteria_snapshot_id, id),
    INDEX idx_matching_package_parent (parent_package_id, id),
    INDEX idx_matching_package_state_time (package_state, created_at_utc),
    CONSTRAINT fk_matching_package_criteria FOREIGN KEY (criteria_snapshot_id)
        REFERENCES matching_coordination_criteria_snapshots(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_package_parent FOREIGN KEY (parent_package_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_package_identity CHECK (
        CHAR_LENGTH(TRIM(package_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
    ),
    CONSTRAINT chk_matching_package_payload CHECK (
        JSON_TYPE(package_snapshot) = 'OBJECT' AND JSON_LENGTH(package_snapshot) > 0
    ),
    CONSTRAINT chk_matching_package_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_package_digest CHECK (package_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_matching_package_actor CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0),
    CONSTRAINT chk_matching_package_parent CHECK (
        (lineage_kind = 'initial' AND parent_package_id IS NULL)
        OR (lineage_kind <> 'initial' AND parent_package_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    criteria_snapshot_id BIGINT UNSIGNED NOT NULL,
    package_lineage_id BIGINT UNSIGNED NULL,
    event_type ENUM(
        'criteria_snapshotted','package_proposed','candidate_contacted',
        'caregiver_willingness','customer_decision','criteria_diff',
        'rematch_required','conversion_requested','stale','superseded'
    ) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    event_payload JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    event_digest CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_event_id (event_id),
    UNIQUE KEY uq_matching_event_idempotency (idempotency_key),
    INDEX idx_matching_event_case_time (case_no, id),
    INDEX idx_matching_event_criteria (criteria_snapshot_id, id),
    INDEX idx_matching_event_package_time (package_lineage_id, id),
    INDEX idx_matching_event_type_time (event_type, created_at_utc),
    CONSTRAINT fk_matching_event_criteria FOREIGN KEY (criteria_snapshot_id)
        REFERENCES matching_coordination_criteria_snapshots(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_event_package FOREIGN KEY (package_lineage_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_event_identity CHECK (
        CHAR_LENGTH(TRIM(event_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
        AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_matching_event_payload CHECK (
        JSON_TYPE(event_payload) = 'OBJECT' AND JSON_LENGTH(event_payload) > 0
    ),
    CONSTRAINT chk_matching_event_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_event_versions CHECK (resulting_version >= expected_version),
    CONSTRAINT chk_matching_event_digest CHECK (event_digest REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_matching_event_actor CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_apply_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    receipt_id VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    criteria_snapshot_id BIGINT UNSIGNED NOT NULL,
    package_lineage_id BIGINT UNSIGNED NULL,
    command_name VARCHAR(96) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NULL,
    source_version_tuple JSON NOT NULL,
    result_snapshot JSON NOT NULL,
    outcome_state ENUM('applied','replayed','rematch_required','rejected_as_stale','conflict') NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    applied_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_receipt_id (receipt_id),
    UNIQUE KEY uq_matching_receipt_idempotency (idempotency_key),
    INDEX idx_matching_receipt_event (event_id, id),
    INDEX idx_matching_receipt_criteria (criteria_snapshot_id, id),
    INDEX idx_matching_receipt_package (package_lineage_id, id),
    INDEX idx_matching_receipt_outcome_time (outcome_state, created_at_utc),
    CONSTRAINT fk_matching_receipt_event FOREIGN KEY (event_id)
        REFERENCES matching_coordination_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_receipt_criteria FOREIGN KEY (criteria_snapshot_id)
        REFERENCES matching_coordination_criteria_snapshots(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_receipt_package FOREIGN KEY (package_lineage_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_receipt_identity CHECK (
        CHAR_LENGTH(TRIM(receipt_id)) > 0 AND CHAR_LENGTH(TRIM(command_name)) > 0
        AND CHAR_LENGTH(TRIM(idempotency_key)) > 0 AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_matching_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND (preview_fingerprint IS NULL OR preview_fingerprint REGEXP '^[0-9a-f]{64}$')
    ),
    CONSTRAINT chk_matching_receipt_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_receipt_result CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT' AND JSON_LENGTH(result_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_coordination_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    reference_id VARCHAR(191) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    receipt_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    intent_type ENUM(
        'line_matching_interaction','line_criteria_diff_resend',
        'assignment_conversion_requested','rematch_requested',
        'orders_terms_update_requested'
    ) NOT NULL,
    target_owner ENUM('line_integration','assignment_workflow','orders_workflow') NOT NULL,
    intent_payload JSON NOT NULL,
    source_version_tuple JSON NOT NULL,
    reference_digest CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_outbox_reference_id (reference_id),
    UNIQUE KEY uq_matching_outbox_idempotency (idempotency_key),
    INDEX idx_matching_outbox_event (event_id, id),
    INDEX idx_matching_outbox_receipt (receipt_id, id),
    INDEX idx_matching_outbox_created_time (created_at_utc, id),
    INDEX idx_matching_outbox_case (case_no, id),
    CONSTRAINT fk_matching_outbox_event FOREIGN KEY (event_id)
        REFERENCES matching_coordination_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_outbox_receipt FOREIGN KEY (receipt_id)
        REFERENCES matching_coordination_apply_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_outbox_identity CHECK (
        CHAR_LENGTH(TRIM(reference_id)) > 0 AND CHAR_LENGTH(TRIM(case_no)) > 0
        AND CHAR_LENGTH(TRIM(idempotency_key)) > 0 AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_matching_outbox_target CHECK (
        (intent_type IN ('line_matching_interaction','line_criteria_diff_resend')
            AND target_owner = 'line_integration')
        OR (intent_type IN ('assignment_conversion_requested','rematch_requested')
            AND target_owner = 'assignment_workflow')
        OR (intent_type = 'orders_terms_update_requested'
            AND target_owner = 'orders_workflow')
    ),
    CONSTRAINT chk_matching_outbox_payload CHECK (
        JSON_TYPE(intent_payload) = 'OBJECT' AND JSON_LENGTH(intent_payload) > 0
    ),
    CONSTRAINT chk_matching_outbox_sources CHECK (
        JSON_TYPE(source_version_tuple) = 'ARRAY' AND JSON_LENGTH(source_version_tuple) > 0
    ),
    CONSTRAINT chk_matching_outbox_digest CHECK (reference_digest REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_matching_criteria_snapshots_before_update;
CREATE TRIGGER trg_matching_criteria_snapshots_before_update
BEFORE UPDATE ON matching_coordination_criteria_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_criteria_snapshots records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_criteria_snapshots_before_delete;
CREATE TRIGGER trg_matching_criteria_snapshots_before_delete
BEFORE DELETE ON matching_coordination_criteria_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_criteria_snapshots records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_package_lineage_before_update;
CREATE TRIGGER trg_matching_package_lineage_before_update
BEFORE UPDATE ON matching_coordination_package_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_package_lineage records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_package_lineage_before_delete;
CREATE TRIGGER trg_matching_package_lineage_before_delete
BEFORE DELETE ON matching_coordination_package_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_package_lineage records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_coordination_events_before_update;
CREATE TRIGGER trg_matching_coordination_events_before_update
BEFORE UPDATE ON matching_coordination_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_events records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_coordination_events_before_delete;
CREATE TRIGGER trg_matching_coordination_events_before_delete
BEFORE DELETE ON matching_coordination_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_apply_receipts_before_update;
CREATE TRIGGER trg_matching_apply_receipts_before_update
BEFORE UPDATE ON matching_coordination_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_apply_receipts records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_apply_receipts_before_delete;
CREATE TRIGGER trg_matching_apply_receipts_before_delete
BEFORE DELETE ON matching_coordination_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_apply_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_outbox_before_update;
CREATE TRIGGER trg_matching_outbox_before_update
BEFORE UPDATE ON matching_coordination_outbox
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_outbox records cannot be updated';
DROP TRIGGER IF EXISTS trg_matching_outbox_before_delete;
CREATE TRIGGER trg_matching_outbox_before_delete
BEFORE DELETE ON matching_coordination_outbox
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_outbox records cannot be deleted';

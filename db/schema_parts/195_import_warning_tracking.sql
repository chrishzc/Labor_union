-- File: 195_import_warning_tracking.sql
-- Description: 新增 WP90 匯入欄位警示、追蹤事件、待辦投影、重送關聯、receipt 與 outbox。

CREATE TABLE IF NOT EXISTS import_warning_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    occurrence_identity VARCHAR(191) NOT NULL,
    owning_lane VARCHAR(64) NOT NULL,
    source_kind VARCHAR(64) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_receipt_identity VARCHAR(191) NULL,
    logical_code VARCHAR(96) NOT NULL,
    field_path VARCHAR(191) NOT NULL,
    masked_subject VARCHAR(191) NOT NULL,
    issue_codes JSON NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_occurrence_identity (occurrence_identity),
    UNIQUE KEY uq_import_warning_occurrence_source (
        owning_lane, source_event_identity, logical_code, field_path
    ),
    INDEX idx_import_warning_occurrence_lane_subject (owning_lane, masked_subject),
    CONSTRAINT chk_import_warning_occurrence_payload
        CHECK (JSON_TYPE(issue_codes) = 'ARRAY' AND JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_tracking_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    occurrence_id BIGINT NOT NULL,
    action ENUM(
        'opened', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NOT NULL,
    before_status ENUM(
        'open', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NULL,
    after_status ENUM(
        'open', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_kind ENUM('union_operator', 'system') NOT NULL,
    actor_identity VARCHAR(100) NOT NULL,
    reason_code VARCHAR(100) NOT NULL,
    note VARCHAR(500) NULL,
    evidence_reference VARCHAR(191) NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_tracking_event_identity (event_identity),
    UNIQUE KEY uq_import_warning_tracking_event_key (idempotency_key),
    INDEX idx_import_warning_tracking_event_occurrence (occurrence_id, resulting_version),
    CONSTRAINT fk_import_warning_tracking_event_occurrence
        FOREIGN KEY (occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_tracking_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_import_warning_tracking_event_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_current_tasks (
    occurrence_id BIGINT PRIMARY KEY,
    tracking_status ENUM(
        'open', 'awaiting_external_confirmation', 'response_recorded',
        'reimport_requested', 'closed', 'auto_resolved'
    ) NOT NULL,
    tracking_version BIGINT UNSIGNED NOT NULL,
    replacement_occurrence_id BIGINT NULL,
    last_event_id BIGINT NOT NULL,
    last_event_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_import_warning_current_active (tracking_status, last_event_at),
    CONSTRAINT fk_import_warning_current_occurrence
        FOREIGN KEY (occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_current_replacement
        FOREIGN KEY (replacement_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_current_event
        FOREIGN KEY (last_event_id) REFERENCES import_warning_tracking_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_current_version CHECK (tracking_version > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_resubmission_associations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    association_identity VARCHAR(191) NOT NULL,
    prior_occurrence_id BIGINT NOT NULL,
    owning_lane VARCHAR(64) NOT NULL,
    prior_source_event_identity VARCHAR(191) NOT NULL,
    new_source_event_identity VARCHAR(191) NOT NULL,
    new_receipt_identity VARCHAR(191) NOT NULL,
    import_outcome ENUM('failed', 'succeeded') NOT NULL,
    replacement_occurrence_id BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_resubmission_identity (association_identity),
    UNIQUE KEY uq_import_warning_resubmission_new_source (owning_lane, new_source_event_identity),
    CONSTRAINT fk_import_warning_resubmission_prior
        FOREIGN KEY (prior_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_resubmission_replacement
        FOREIGN KEY (replacement_occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_resubmission_links
        CHECK (
            (import_outcome = 'failed' AND replacement_occurrence_id IS NOT NULL)
            OR (import_outcome = 'succeeded' AND replacement_occurrence_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_tracking_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    occurrence_id BIGINT NOT NULL,
    tracking_event_id BIGINT NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_tracking_receipt_key (idempotency_key),
    UNIQUE KEY uq_import_warning_tracking_receipt_event (tracking_event_id),
    CONSTRAINT fk_import_warning_tracking_receipt_occurrence
        FOREIGN KEY (occurrence_id) REFERENCES import_warning_occurrences(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_import_warning_tracking_receipt_event
        FOREIGN KEY (tracking_event_id) REFERENCES import_warning_tracking_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_tracking_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_import_warning_tracking_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_warning_tracking_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tracking_event_id BIGINT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_import_warning_tracking_outbox_intent (intent_key),
    INDEX idx_import_warning_tracking_outbox_pending (published_at, attempts, id),
    CONSTRAINT fk_import_warning_tracking_outbox_event
        FOREIGN KEY (tracking_event_id) REFERENCES import_warning_tracking_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_import_warning_tracking_outbox_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_import_warning_tracking_outbox_attempts CHECK (attempts >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_import_warning_occurrences_before_update;
CREATE TRIGGER trg_import_warning_occurrences_before_update
BEFORE UPDATE ON import_warning_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_occurrences records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_occurrences_before_delete;
CREATE TRIGGER trg_import_warning_occurrences_before_delete
BEFORE DELETE ON import_warning_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_occurrences records cannot be deleted';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_events_before_update;
CREATE TRIGGER trg_import_warning_tracking_events_before_update
BEFORE UPDATE ON import_warning_tracking_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_events_before_delete;
CREATE TRIGGER trg_import_warning_tracking_events_before_delete
BEFORE DELETE ON import_warning_tracking_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_import_warning_resubmission_associations_before_update;
CREATE TRIGGER trg_import_warning_resubmission_associations_before_update
BEFORE UPDATE ON import_warning_resubmission_associations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_resubmission_associations records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_resubmission_associations_before_delete;
CREATE TRIGGER trg_import_warning_resubmission_associations_before_delete
BEFORE DELETE ON import_warning_resubmission_associations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_resubmission_associations records cannot be deleted';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_receipts_before_update;
CREATE TRIGGER trg_import_warning_tracking_receipts_before_update
BEFORE UPDATE ON import_warning_tracking_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_import_warning_tracking_receipts_before_delete;
CREATE TRIGGER trg_import_warning_tracking_receipts_before_delete
BEFORE DELETE ON import_warning_tracking_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_receipts records cannot be deleted';

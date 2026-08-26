-- File: 1004_controlled_file_storage_foundation.sql
-- Description: 建立受控檔案 staging、版本、Apply、cleanup 與 reconciliation 的 additive schema。

CREATE TABLE IF NOT EXISTS controlled_file_staging_objects (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    staging_id VARCHAR(64) NOT NULL,
    storage_locator VARCHAR(500) NOT NULL,
    owner_type ENUM(
        'contract_signing', 'scheduling', 'orders', 'staff', 'line_integration'
    ) NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    object_key VARCHAR(191) NOT NULL,
    purpose ENUM(
        'final_signed_contract', 'service_date_confirmation', 'baby_log_photo',
        'meal_photo', 'order_notice', 'staff_resume', 'staff_certificate',
        'staff_health_exam', 'rich_menu_background'
    ) NOT NULL,
    logical_folder VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    staging_state ENUM('staged', 'applied', 'quarantined', 'cleaned')
        NOT NULL DEFAULT 'staged',
    staging_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    created_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at_utc DATETIME(6) NOT NULL,
    applied_at_utc DATETIME(6) NULL,
    cleaned_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_controlled_file_staging_id (staging_id),
    UNIQUE KEY uq_controlled_file_staging_locator (storage_locator),
    UNIQUE KEY uq_controlled_file_staging_idempotency (idempotency_key),
    INDEX idx_controlled_file_staging_owner (
        owner_type, subject_reference, purpose, staging_state, id
    ),
    INDEX idx_controlled_file_staging_cleanup (
        staging_state, expires_at_utc, id
    ),
    CONSTRAINT chk_controlled_file_staging_identity CHECK (
        staging_id REGEXP '^cfs_[0-9a-f]{32}$'
        AND CHAR_LENGTH(TRIM(storage_locator)) > 0
        AND CHAR_LENGTH(TRIM(subject_reference)) > 0
        AND CHAR_LENGTH(TRIM(object_key)) > 0
        AND CHAR_LENGTH(TRIM(purpose)) > 0
        AND CHAR_LENGTH(TRIM(original_filename)) > 0
        AND CHAR_LENGTH(TRIM(content_type)) > 0
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND CHAR_LENGTH(TRIM(created_by_actor)) > 0
        AND size_bytes > 0
        AND expires_at_utc > created_at_utc
    ),
    CONSTRAINT chk_controlled_file_staging_digest CHECK (
        content_sha256 REGEXP '^[0-9a-f]{64}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_controlled_file_staging_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose = 'final_signed_contract')
        OR (owner_type = 'scheduling' AND purpose IN (
            'service_date_confirmation', 'baby_log_photo', 'meal_photo'
        ))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN (
            'staff_resume', 'staff_certificate', 'staff_health_exam'
        ))
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    ),
    CONSTRAINT chk_controlled_file_staging_state CHECK (
        (staging_state = 'applied' AND applied_at_utc IS NOT NULL AND cleaned_at_utc IS NULL)
        OR (staging_state = 'cleaned' AND applied_at_utc IS NULL AND cleaned_at_utc IS NOT NULL)
        OR (staging_state IN ('staged', 'quarantined')
            AND applied_at_utc IS NULL AND cleaned_at_utc IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_objects (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    opaque_object_id VARCHAR(64) NOT NULL,
    source_staging_id BIGINT UNSIGNED NOT NULL,
    owner_type ENUM(
        'contract_signing', 'scheduling', 'orders', 'staff', 'line_integration'
    ) NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    object_key VARCHAR(191) NOT NULL,
    purpose ENUM(
        'final_signed_contract', 'service_date_confirmation', 'baby_log_photo',
        'meal_photo', 'order_notice', 'staff_resume', 'staff_certificate',
        'staff_health_exam', 'rich_menu_background'
    ) NOT NULL,
    logical_folder VARCHAR(500) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    storage_locator VARCHAR(500) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    version_number BIGINT UNSIGNED NOT NULL,
    supersedes_object_id BIGINT UNSIGNED NULL,
    supersedes_version_number BIGINT UNSIGNED NULL,
    created_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_object_id (opaque_object_id),
    UNIQUE KEY uq_controlled_file_object_staging (source_staging_id),
    UNIQUE KEY uq_controlled_file_object_locator (storage_locator),
    UNIQUE KEY uq_controlled_file_owner_version (
        owner_type, subject_reference, object_key, version_number
    ),
    UNIQUE KEY uq_controlled_file_version_identity (
        id, owner_type, subject_reference, object_key, purpose, version_number
    ),
    INDEX idx_controlled_file_object_owner (
        owner_type, subject_reference, purpose, id
    ),
    INDEX idx_controlled_file_object_supersedes (supersedes_object_id, id),
    CONSTRAINT fk_controlled_file_object_staging FOREIGN KEY (source_staging_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_object_supersedes FOREIGN KEY (
        supersedes_object_id, owner_type, subject_reference, object_key,
        purpose, supersedes_version_number
    ) REFERENCES controlled_file_objects (
        id, owner_type, subject_reference, object_key, purpose, version_number
    )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_object_identity CHECK (
        opaque_object_id REGEXP '^cf_[0-9a-f]{32}$'
        AND CHAR_LENGTH(TRIM(subject_reference)) > 0
        AND CHAR_LENGTH(TRIM(object_key)) > 0
        AND CHAR_LENGTH(TRIM(purpose)) > 0
        AND CHAR_LENGTH(TRIM(filename)) > 0
        AND CHAR_LENGTH(TRIM(storage_locator)) > 0
        AND CHAR_LENGTH(TRIM(content_type)) > 0
        AND CHAR_LENGTH(TRIM(created_by_actor)) > 0
        AND size_bytes > 0
        AND version_number > 0
    ),
    CONSTRAINT chk_controlled_file_object_digest CHECK (
        content_sha256 REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_controlled_file_object_chain CHECK (
        (supersedes_object_id IS NULL
            AND supersedes_version_number IS NULL AND version_number = 1)
        OR (supersedes_object_id IS NOT NULL
            AND supersedes_version_number IS NOT NULL
            AND version_number = supersedes_version_number + 1)
    ),
    CONSTRAINT chk_controlled_file_object_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose = 'final_signed_contract')
        OR (owner_type = 'scheduling' AND purpose IN (
            'service_date_confirmation', 'baby_log_photo', 'meal_photo'
        ))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN (
            'staff_resume', 'staff_certificate', 'staff_health_exam'
        ))
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_apply_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    receipt_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NOT NULL,
    controlled_object_id BIGINT UNSIGNED NOT NULL,
    command_type ENUM('controlled_file_apply') NOT NULL,
    schema_version ENUM('controlled-file-apply-receipt.v1') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    expected_staging_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    outcome_state ENUM('created') NOT NULL DEFAULT 'created',
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    applied_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_receipt_id (receipt_id),
    UNIQUE KEY uq_controlled_file_receipt_idempotency (idempotency_key),
    UNIQUE KEY uq_controlled_file_receipt_staging (staging_object_id),
    UNIQUE KEY uq_controlled_file_receipt_object (controlled_object_id),
    CONSTRAINT fk_controlled_file_receipt_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_receipt_object FOREIGN KEY (controlled_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_receipt_identity CHECK (
        receipt_id REGEXP '^cfr_[0-9a-f]{32}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        AND expected_staging_version > 0
    ),
    CONSTRAINT chk_controlled_file_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_controlled_file_receipt_result CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT'
        AND JSON_LENGTH(result_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_reconciliation_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NULL,
    controlled_object_id BIGINT UNSIGNED NULL,
    outcome ENUM(
        'exact', 'missing_object', 'digest_mismatch', 'orphan_object', 'still_writing'
    ) NOT NULL,
    observation_fingerprint CHAR(64) NOT NULL,
    observed_sha256 CHAR(64) NULL,
    observed_size_bytes BIGINT UNSIGNED NULL,
    observation_snapshot JSON NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    observed_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_reconciliation_event (event_id),
    UNIQUE KEY uq_controlled_file_reconciliation_fingerprint (observation_fingerprint),
    INDEX idx_controlled_file_reconciliation_staging (staging_object_id, id),
    INDEX idx_controlled_file_reconciliation_object (controlled_object_id, id),
    INDEX idx_controlled_file_reconciliation_outcome (outcome, observed_at_utc, id),
    CONSTRAINT fk_controlled_file_reconciliation_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_reconciliation_object FOREIGN KEY (controlled_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_reconciliation_identity CHECK (
        event_id REGEXP '^cfe_[0-9a-f]{32}$'
        AND observation_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        AND (
            (outcome IN ('exact', 'missing_object', 'digest_mismatch')
                AND controlled_object_id IS NOT NULL)
            OR (outcome IN ('orphan_object', 'still_writing')
                AND staging_object_id IS NOT NULL AND controlled_object_id IS NULL)
        )
    ),
    CONSTRAINT chk_controlled_file_reconciliation_observation CHECK (
        (outcome IN ('exact', 'digest_mismatch')
            AND observed_sha256 REGEXP '^[0-9a-f]{64}$'
            AND observed_size_bytes IS NOT NULL)
        OR (outcome = 'missing_object'
            AND observed_sha256 IS NULL AND observed_size_bytes IS NULL)
        OR (outcome IN ('orphan_object', 'still_writing')
            AND (observed_sha256 IS NULL
                OR observed_sha256 REGEXP '^[0-9a-f]{64}$'))
    ),
    CONSTRAINT chk_controlled_file_reconciliation_snapshot CHECK (
        JSON_TYPE(observation_snapshot) = 'OBJECT'
        AND JSON_LENGTH(observation_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_cleanup_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cleanup_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NOT NULL,
    event_sequence TINYINT UNSIGNED NOT NULL,
    event_type ENUM('intent', 'completed', 'reconciliation_required') NOT NULL,
    reason ENUM('expired', 'abandoned') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    expected_staging_version BIGINT UNSIGNED NOT NULL,
    expected_sha256 CHAR(64) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    error_code VARCHAR(100) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_cleanup_event (event_id),
    UNIQUE KEY uq_controlled_file_cleanup_sequence (cleanup_id, event_sequence),
    UNIQUE KEY uq_controlled_file_cleanup_idempotency_sequence (
        idempotency_key, event_sequence
    ),
    INDEX idx_controlled_file_cleanup_staging (
        staging_object_id, event_sequence, id
    ),
    INDEX idx_controlled_file_cleanup_terminal (
        event_type, occurred_at_utc, id
    ),
    CONSTRAINT fk_controlled_file_cleanup_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_cleanup_identity CHECK (
        cleanup_id REGEXP '^cfc_[0-9a-f]{32}$'
        AND event_id REGEXP '^cfce_[0-9a-f]{32}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND expected_staging_version > 0
        AND expected_sha256 REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_controlled_file_cleanup_event CHECK (
        (event_sequence = 1 AND event_type = 'intent' AND error_code IS NULL)
        OR (event_sequence = 2 AND event_type = 'completed' AND error_code IS NULL)
        OR (event_sequence = 2
            AND event_type = 'reconciliation_required'
            AND error_code IS NOT NULL
            AND CHAR_LENGTH(TRIM(error_code)) > 0)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_controlled_file_objects_before_update;
CREATE TRIGGER trg_controlled_file_objects_before_update
BEFORE UPDATE ON controlled_file_objects FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_objects records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_objects_before_delete;
CREATE TRIGGER trg_controlled_file_objects_before_delete
BEFORE DELETE ON controlled_file_objects FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_objects records cannot be deleted';

DROP TRIGGER IF EXISTS trg_controlled_file_apply_receipts_before_update;
CREATE TRIGGER trg_controlled_file_apply_receipts_before_update
BEFORE UPDATE ON controlled_file_apply_receipts FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_apply_receipts_before_delete;
CREATE TRIGGER trg_controlled_file_apply_receipts_before_delete
BEFORE DELETE ON controlled_file_apply_receipts FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_apply_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_controlled_file_reconciliation_events_before_update;
CREATE TRIGGER trg_controlled_file_reconciliation_events_before_update
BEFORE UPDATE ON controlled_file_reconciliation_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_reconciliation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_reconciliation_events_before_delete;
CREATE TRIGGER trg_controlled_file_reconciliation_events_before_delete
BEFORE DELETE ON controlled_file_reconciliation_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_reconciliation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_controlled_file_cleanup_events_before_update;
CREATE TRIGGER trg_controlled_file_cleanup_events_before_update
BEFORE UPDATE ON controlled_file_cleanup_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_cleanup_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_controlled_file_cleanup_events_before_delete;
CREATE TRIGGER trg_controlled_file_cleanup_events_before_delete
BEFORE DELETE ON controlled_file_cleanup_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_cleanup_events records cannot be deleted';

-- File: 1015_controlled_file_reference_finalize_leases.sql
-- Description: 1015 additive reference-aware finalize, Scheduling bridge and leases.
-- This part is schema-only: no seed, backfill, provider operation, or byte deletion.
-- Pre-successor rows remain legacy-readable; controlled_file_object_id is not backfilled.
-- finalize_state='available' means bytes passed digest/size integrity verification.

ALTER TABLE scheduling_service_day_log_attachments
    MODIFY COLUMN provider_media_id VARCHAR(191) NULL,
    ADD COLUMN controlled_file_object_id BIGINT UNSIGNED NULL,
    ADD UNIQUE KEY uq_scheduling_service_day_log_attachment_controlled_file (
        controlled_file_object_id
    ),
    ADD CONSTRAINT fk_scheduling_service_day_log_attachment_controlled_file
        FOREIGN KEY (controlled_file_object_id) REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT chk_scheduling_service_day_log_attachment_reference_source CHECK (
        (provider_media_id IS NOT NULL AND controlled_file_object_id IS NULL)
        OR (provider_media_id IS NULL AND controlled_file_object_id IS NOT NULL)
    );

CREATE TABLE IF NOT EXISTS controlled_file_finalize_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    finalize_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NOT NULL,
    controlled_file_object_id BIGINT UNSIGNED NOT NULL,
    expected_sha256 CHAR(64) NOT NULL,
    finalize_state ENUM(
        'pending', 'processing', 'available', 'reconciliation_required'
    ) NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    claimed_by VARCHAR(191) NULL,
    claim_token VARCHAR(191) NULL,
    claimed_at_utc DATETIME(6) NULL,
    observed_sha256 CHAR(64) NULL,
    observed_size_bytes BIGINT UNSIGNED NULL,
    last_error_code VARCHAR(128) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    available_at_utc DATETIME(6) NULL,
    failed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_controlled_file_finalize_id (finalize_id),
    UNIQUE KEY uq_controlled_file_finalize_staging (staging_object_id),
    UNIQUE KEY uq_controlled_file_finalize_object (controlled_file_object_id),
    INDEX idx_controlled_file_finalize_claim (
        finalize_state, claimed_at_utc, id
    ),
    CONSTRAINT fk_controlled_file_finalize_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_finalize_object FOREIGN KEY (controlled_file_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_finalize_identity CHECK (
        finalize_id REGEXP '^cff_[0-9a-f]{32}$'
        AND expected_sha256 REGEXP '^[0-9a-f]{64}$'
        AND (claimed_by IS NULL OR CHAR_LENGTH(TRIM(claimed_by)) > 0)
        AND (claim_token IS NULL OR CHAR_LENGTH(TRIM(claim_token)) > 0)
        AND attempt_count >= 0
    ),
    CONSTRAINT chk_controlled_file_finalize_observation CHECK (
        (observed_sha256 IS NULL AND observed_size_bytes IS NULL)
        OR (observed_sha256 REGEXP '^[0-9a-f]{64}$' AND observed_size_bytes > 0)
    ),
    CONSTRAINT chk_controlled_file_finalize_state CHECK (
        (finalize_state = 'pending'
            AND claimed_by IS NULL AND claimed_at_utc IS NULL
            AND available_at_utc IS NULL AND failed_at_utc IS NULL)
        OR (finalize_state = 'processing'
            AND claimed_by IS NOT NULL AND claimed_at_utc IS NOT NULL
            AND available_at_utc IS NULL AND failed_at_utc IS NULL)
        OR (finalize_state = 'available'
            AND available_at_utc IS NOT NULL AND failed_at_utc IS NULL
            AND observed_sha256 IS NOT NULL AND observed_size_bytes > 0)
        OR (finalize_state = 'reconciliation_required'
            AND failed_at_utc IS NOT NULL AND last_error_code IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_references (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    reference_id VARCHAR(64) NOT NULL,
    controlled_file_object_id BIGINT UNSIGNED NOT NULL,
    service_day_log_attachment_id BIGINT UNSIGNED NOT NULL,
    reference_kind ENUM('scheduling_service_day_log_attachment') NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_controlled_file_reference_id (reference_id),
    UNIQUE KEY uq_controlled_file_reference_object (controlled_file_object_id),
    UNIQUE KEY uq_controlled_file_reference_attachment (service_day_log_attachment_id),
    CONSTRAINT fk_controlled_file_reference_object FOREIGN KEY (controlled_file_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_controlled_file_reference_attachment FOREIGN KEY (
        service_day_log_attachment_id
    ) REFERENCES scheduling_service_day_log_attachments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_reference_identity CHECK (
        reference_id REGEXP '^cfrf_[0-9a-f]{32}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS controlled_file_leases (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    lease_id VARCHAR(64) NOT NULL,
    staging_object_id BIGINT UNSIGNED NOT NULL,
    holder VARCHAR(191) NOT NULL,
    lease_state ENUM('active', 'released', 'expired') NOT NULL DEFAULT 'active',
    acquired_at_utc DATETIME(6) NOT NULL,
    expires_at_utc DATETIME(6) NOT NULL,
    released_at_utc DATETIME(6) NULL,
    active_staging_object_id BIGINT UNSIGNED GENERATED ALWAYS AS (
        CASE WHEN lease_state = 'active' THEN staging_object_id ELSE NULL END
    ) STORED,
    UNIQUE KEY uq_controlled_file_lease_id (lease_id),
    UNIQUE KEY uq_controlled_file_active_staging (active_staging_object_id),
    INDEX idx_controlled_file_lease_expiry (lease_state, expires_at_utc, id),
    CONSTRAINT fk_controlled_file_lease_staging FOREIGN KEY (staging_object_id)
        REFERENCES controlled_file_staging_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_controlled_file_lease_identity CHECK (
        lease_id REGEXP '^cfl_[0-9a-f]{32}$'
        AND CHAR_LENGTH(TRIM(holder)) > 0
        AND expires_at_utc > acquired_at_utc
    ),
    CONSTRAINT chk_controlled_file_lease_state CHECK (
        (lease_state = 'active' AND released_at_utc IS NULL)
        OR (lease_state IN ('released', 'expired') AND released_at_utc IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_controlled_file_references_before_update
BEFORE UPDATE ON controlled_file_references
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'controlled_file_references cannot be updated';

CREATE TRIGGER trg_controlled_file_references_before_delete
BEFORE DELETE ON controlled_file_references
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'controlled_file_references cannot be deleted';

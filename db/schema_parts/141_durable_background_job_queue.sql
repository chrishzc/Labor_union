-- Additive queue metadata.  Existing in-process jobs remain readable while
-- newly submitted durable commands carry a complete replayable envelope.
ALTER TABLE background_jobs
    ADD COLUMN command_type VARCHAR(191) NULL AFTER command_identity,
    ADD COLUMN command_version SMALLINT UNSIGNED NULL AFTER command_type,
    ADD COLUMN command_payload JSON NULL AFTER command_version,
    ADD COLUMN submitted_by VARCHAR(191) NULL AFTER command_payload,
    ADD COLUMN correlation_id VARCHAR(191) NULL AFTER submitted_by,
    ADD COLUMN available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) AFTER error_payload,
    ADD COLUMN attempt_count SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER available_at,
    ADD COLUMN max_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 3 AFTER attempt_count,
    ADD COLUMN lease_token VARCHAR(191) NULL AFTER max_attempts,
    ADD COLUMN lease_owner VARCHAR(191) NULL AFTER lease_token,
    ADD COLUMN lease_expires_at DATETIME(6) NULL AFTER lease_owner,
    ADD COLUMN result_reference VARCHAR(191) NULL AFTER lease_expires_at,
    ADD COLUMN completed_at DATETIME(6) NULL AFTER result_reference;

CREATE INDEX idx_background_jobs_queue
    ON background_jobs (status, available_at, created_at);

CREATE INDEX idx_background_jobs_lease
    ON background_jobs (status, lease_expires_at);

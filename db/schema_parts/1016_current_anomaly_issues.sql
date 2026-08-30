-- Additive current-only anomaly successor.
-- This part deliberately creates no occurrence, workflow, claim, resolve,
-- reclassification, timeline, history, or anomaly-specific delivery table.
CREATE TABLE IF NOT EXISTS current_anomaly_issues (
    issue_key CHAR(67) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    definition_code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    owner_domain VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    owner_root_type VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    subject_type VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    subject_id VARCHAR(191) NOT NULL,
    subject_identity JSON NOT NULL,
    owner_snapshot_token VARCHAR(191) NOT NULL,
    owner_version BIGINT UNSIGNED NOT NULL,
    severity ENUM('warning', 'blocking') NOT NULL,
    blocking TINYINT(1) NOT NULL,
    details_version SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    details JSON NOT NULL,
    episode_started_at DATETIME(6) NOT NULL,
    last_verified_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (issue_key),
    INDEX idx_current_anomaly_owner (
        owner_domain, owner_root_type, subject_type, subject_id, issue_key
    ),
    INDEX idx_current_anomaly_definition (
        definition_code, blocking, severity, episode_started_at, issue_key
    ),
    CONSTRAINT chk_current_anomaly_issue_key
        CHECK (issue_key REGEXP '^ci_[0-9a-f]{64}$'),
    CONSTRAINT chk_current_anomaly_subject_identity
        CHECK (JSON_TYPE(subject_identity) = 'OBJECT'),
    CONSTRAINT chk_current_anomaly_details
        CHECK (details_version = 1 AND JSON_TYPE(details) = 'OBJECT'),
    CONSTRAINT chk_current_anomaly_boolean
        CHECK (blocking IN (0, 1)),
    CONSTRAINT chk_current_anomaly_time_order
        CHECK (last_verified_at >= episode_started_at),
    CONSTRAINT chk_current_anomaly_text
        CHECK (
            CHAR_LENGTH(TRIM(definition_code)) > 0
            AND CHAR_LENGTH(TRIM(owner_domain)) > 0
            AND CHAR_LENGTH(TRIM(owner_root_type)) > 0
            AND CHAR_LENGTH(TRIM(subject_type)) > 0
            AND CHAR_LENGTH(TRIM(subject_id)) > 0
            AND CHAR_LENGTH(TRIM(owner_snapshot_token)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

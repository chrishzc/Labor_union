ALTER TABLE line_identity_bindings
    MODIFY COLUMN binding_status ENUM(
        'unbound','pending_review','bound','revocation_pending','revoked'
    ) NOT NULL DEFAULT 'unbound';

ALTER TABLE line_identity_bindings
    MODIFY COLUMN active_subject_key VARCHAR(400)
    GENERATED ALWAYS AS (
        CASE
            WHEN binding_status IN ('pending_review','bound','revocation_pending')
            THEN CONCAT(subject_type, ':', subject_reference)
            ELSE NULL
        END
    ) STORED;

ALTER TABLE line_identity_binding_events
    MODIFY COLUMN action ENUM(
        'claim_submitted','bound','revocation_requested','revoked','rebound',
        'legacy_imported'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS line_identity_revocation_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(191) NOT NULL,
    subject_type ENUM('customer','staff','admin') NOT NULL,
    subject_reference VARCHAR(191) NOT NULL,
    request_status ENUM(
        'pending_menu_reset','menu_reset_failed','completed','manual_completed'
    ) NOT NULL DEFAULT 'pending_menu_reset',
    requested_binding_version BIGINT UNSIGNED NOT NULL,
    pending_binding_version BIGINT UNSIGNED NOT NULL,
    completed_binding_version BIGINT UNSIGNED NULL,
    default_menu_publication_id BIGINT NOT NULL,
    provider_menu_id VARCHAR(191) NOT NULL,
    requested_by_actor_id VARCHAR(191) NOT NULL,
    request_reason VARCHAR(1000) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    last_error_code VARCHAR(191) NULL,
    last_error_message VARCHAR(1000) NULL,
    requested_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    menu_reset_at_utc DATETIME(6) NULL,
    completed_at_utc DATETIME(6) NULL,
    completed_by_actor_id VARCHAR(191) NULL,
    completion_reason VARCHAR(1000) NULL,
    active_marker TINYINT GENERATED ALWAYS AS (
        CASE
            WHEN request_status IN ('pending_menu_reset','menu_reset_failed')
            THEN 1
            ELSE NULL
        END
    ) STORED,
    UNIQUE KEY uq_line_identity_revocation_idempotency (idempotency_key),
    UNIQUE KEY uq_line_identity_active_revocation (line_user_id, active_marker),
    INDEX idx_line_identity_revocation_status (request_status, requested_at_utc),
    CONSTRAINT fk_line_identity_revocation_binding FOREIGN KEY (line_user_id)
        REFERENCES line_identity_bindings(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_identity_revocation_publication
        FOREIGN KEY (default_menu_publication_id)
        REFERENCES line_rich_menu_publications(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_identity_revocation_version CHECK (
        pending_binding_version = requested_binding_version + 1
        AND (
            completed_binding_version IS NULL
            OR completed_binding_version = pending_binding_version + 1
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

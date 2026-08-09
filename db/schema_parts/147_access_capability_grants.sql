-- Versioned per-admin capability grants; role bundles remain the baseline policy.

CREATE TABLE IF NOT EXISTS admin_capability_grants (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    capability VARCHAR(100) NOT NULL,
    granted_by_admin_user_id BIGINT NOT NULL,
    reason VARCHAR(500) NOT NULL,
    effective_from DATETIME NOT NULL,
    expires_at DATETIME NULL,
    revoked_at DATETIME NULL,
    revoked_by_admin_user_id BIGINT NULL,
    revoked_reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_admin_capability_grant (admin_user_id, capability),
    INDEX idx_admin_capability_effective (admin_user_id, revoked_at, effective_from, expires_at),
    CONSTRAINT fk_capability_grant_admin FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_capability_grant_actor FOREIGN KEY (granted_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_capability_grant_revoke_actor FOREIGN KEY (revoked_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE SET NULL,
    CONSTRAINT chk_capability_grant_period
        CHECK (expires_at IS NULL OR expires_at > effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_control_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    actor_admin_user_id BIGINT NOT NULL,
    event_type ENUM('capability_granted','capability_revoked') NOT NULL,
    capability VARCHAR(100) NOT NULL,
    before_authorization_version BIGINT UNSIGNED NOT NULL,
    after_authorization_version BIGINT UNSIGNED NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_access_control_event_idempotency (idempotency_key),
    INDEX idx_access_control_event_target (admin_user_id, created_at),
    CONSTRAINT fk_access_event_admin FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_access_event_actor FOREIGN KEY (actor_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_access_control_event_version
        CHECK (after_authorization_version = before_authorization_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS access_control_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    receipt_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

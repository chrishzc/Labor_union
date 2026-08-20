-- File: 209_access_control_totp_root.sql
-- Description: 新增 root、TOTP、recovery code、enrollment 與登入嘗試的 Access Control 事實表。

ALTER TABLE admin_users
    ADD COLUMN access_control_version BIGINT UNSIGNED NOT NULL DEFAULT 1
    COMMENT '帳號中心 optimistic-lock version' AFTER role;

CREATE TABLE IF NOT EXISTS admin_root_account (
    singleton_key TINYINT NOT NULL DEFAULT 1,
    admin_user_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (singleton_key),
    UNIQUE KEY uk_admin_root_account_user (admin_user_id),
    CONSTRAINT chk_admin_root_account_singleton CHECK (singleton_key = 1),
    CONSTRAINT fk_admin_root_account_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_totp_factors (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    factor_state ENUM('enrollment_pending','active','revoked') NOT NULL,
    seed_ciphertext TEXT NOT NULL,
    encryption_key_version VARCHAR(64) NOT NULL,
    enrollment_challenge_hash CHAR(64) NOT NULL,
    enrollment_expires_at DATETIME(6) NOT NULL,
    last_successful_step BIGINT NULL,
    activated_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_totp_factor_user (admin_user_id),
    INDEX idx_admin_totp_factor_enrollment (factor_state,enrollment_expires_at),
    CONSTRAINT fk_admin_totp_factor_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_admin_totp_factor_activation CHECK (
        (factor_state = 'active' AND activated_at IS NOT NULL AND revoked_at IS NULL)
        OR (factor_state = 'enrollment_pending' AND activated_at IS NULL AND revoked_at IS NULL)
        OR (factor_state = 'revoked' AND revoked_at IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_mfa_enrollment_challenges (
    id CHAR(36) PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    challenge_hash CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_mfa_challenge_hash (challenge_hash),
    INDEX idx_admin_mfa_challenge_user_expiry (admin_user_id,expires_at,consumed_at),
    CONSTRAINT fk_admin_mfa_challenge_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_totp_recovery_codes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    factor_id BIGINT UNSIGNED NOT NULL,
    code_hash VARCHAR(512) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_totp_recovery_code_hash (code_hash),
    INDEX idx_admin_totp_recovery_factor (factor_id,consumed_at),
    CONSTRAINT fk_admin_totp_recovery_factor FOREIGN KEY (factor_id)
        REFERENCES admin_totp_factors(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username_hash CHAR(64) NOT NULL,
    source_hash CHAR(64) NOT NULL,
    outcome ENUM('failed','succeeded','rate_limited','mfa_replay') NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_admin_login_attempt_subject (username_hash,source_hash,occurred_at),
    INDEX idx_admin_login_attempt_time (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

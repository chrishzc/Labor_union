-- File: 210_access_control_password_challenges.sql
-- Description: 保存兩段式登入的短效 password challenge，綁定 credential、active factor identity 與帳號 access-control version。

CREATE TABLE IF NOT EXISTS admin_password_login_challenges (
    id CHAR(36) PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    credential_version BIGINT UNSIGNED NOT NULL,
    factor_id BIGINT UNSIGNED NOT NULL,
    challenge_hash CHAR(64) NOT NULL,
    source_hash CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_password_login_challenge_hash (challenge_hash),
    INDEX idx_admin_password_login_challenge_expiry (admin_user_id, expires_at, consumed_at),
    CONSTRAINT fk_admin_password_login_challenge_user FOREIGN KEY (admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_admin_password_login_challenge_factor FOREIGN KEY (factor_id)
        REFERENCES admin_totp_factors(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

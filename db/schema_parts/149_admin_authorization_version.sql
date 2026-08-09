-- Additive authorization revision for release-managed dynamic capability grants.
ALTER TABLE admin_users
    ADD COLUMN authorization_version BIGINT UNSIGNED NOT NULL DEFAULT 0
    COMMENT 'effective capability grant revision' AFTER enabled;

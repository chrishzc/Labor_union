-- A session has a sliding idle window but can never outlive its original login.
SET @admin_session_absolute_expiry_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'admin_sessions'
      AND COLUMN_NAME = 'absolute_expires_at'
);
SET @admin_session_schema_sql = IF(
    @admin_session_absolute_expiry_exists = 0,
    'ALTER TABLE `admin_sessions` ADD COLUMN `absolute_expires_at` DATETIME NULL COMMENT ''hard re-authentication deadline'' AFTER `expires_at`',
    'SELECT 1'
);
PREPARE admin_session_schema_stmt FROM @admin_session_schema_sql;
EXECUTE admin_session_schema_stmt;
DEALLOCATE PREPARE admin_session_schema_stmt;

-- A publication may be applied only after the same administrator previewed the
-- current immutable configuration revision.  A later configuration save makes
-- the old preview unusable instead of publishing an unseen menu.
CREATE TABLE IF NOT EXISTS line_rich_menu_publish_previews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    menu_config_id VARCHAR(100) NOT NULL,
    config_revision CHAR(64) NOT NULL,
    config_fingerprint CHAR(64) NOT NULL,
    previewed_by_admin_user_id BIGINT NOT NULL,
    publication_id BIGINT NULL,
    previewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at DATETIME NULL,
    UNIQUE KEY uk_line_menu_preview_snapshot (
        menu_config_id, config_revision, config_fingerprint, previewed_by_admin_user_id
    ),
    INDEX idx_line_menu_preview_apply (menu_config_id, previewed_by_admin_user_id, publication_id),
    CONSTRAINT fk_line_menu_preview_admin FOREIGN KEY (previewed_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_line_menu_preview_publication FOREIGN KEY (publication_id)
        REFERENCES line_rich_menu_publications(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

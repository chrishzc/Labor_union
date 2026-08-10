CREATE TABLE IF NOT EXISTS admin_audit_log_archive (
    source_audit_id BIGINT NOT NULL PRIMARY KEY,
    admin_user_id BIGINT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NULL,
    resource_id VARCHAR(255) NULL,
    request_path VARCHAR(500) NULL,
    http_method VARCHAR(10) NULL,
    result_status INT NULL,
    ip_address VARCHAR(64) NULL,
    details_json JSON NULL,
    created_at DATETIME NOT NULL,
    archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_audit_archive_created_at (created_at),
    INDEX idx_admin_audit_archive_actor_time (admin_user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

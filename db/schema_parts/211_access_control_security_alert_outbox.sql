-- File: 211_access_control_security_alert_outbox.sql
-- Description: 保存 Access Control security audit 的耐久告警投影 intent，供 Incident Worker 非同步重試。

CREATE TABLE IF NOT EXISTS admin_security_alert_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_audit_id BIGINT NOT NULL,
    alert_code VARCHAR(64) NOT NULL,
    alert_identity CHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    processing_status ENUM('pending','processing','completed','dead') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_attempt_at DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at DATETIME(6) NULL,
    last_error_code VARCHAR(64) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uk_admin_security_alert_outbox_audit (source_audit_id),
    INDEX idx_admin_security_alert_outbox_due (processing_status,next_attempt_at,lease_expires_at,id),
    CONSTRAINT fk_admin_security_alert_outbox_audit FOREIGN KEY (source_audit_id)
        REFERENCES admin_audit_logs(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_admin_security_alert_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_admin_security_alert_outbox_attempts CHECK (
        attempt_count <= max_attempts AND max_attempts > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

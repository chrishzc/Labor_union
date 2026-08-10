CREATE TABLE IF NOT EXISTS admin_command_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admin_command_receipt (command_family, idempotency_key),
    CONSTRAINT chk_admin_command_receipt_fingerprints CHECK (
        request_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Orders owns the manual review lifecycle of structured customer change applications.
CREATE TABLE IF NOT EXISTS order_change_requests (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    kind ENUM('service_address','cooking_requirement','daily_service_window','other') NOT NULL,
    before_payload JSON NOT NULL,
    requested_payload JSON NOT NULL,
    idempotency_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    submitted_at DATETIME(6) NOT NULL,
    result VARCHAR(1000) NULL,
    completed_by BIGINT UNSIGNED NULL,
    completed_by_name VARCHAR(100) NULL,
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_order_change_submission (client_id, idempotency_digest),
    KEY idx_order_change_case (case_no, id),
    KEY idx_order_change_pending (completed_at, id),
    CONSTRAINT chk_order_change_completion CHECK (
        (completed_at IS NULL AND result IS NULL AND completed_by IS NULL AND completed_by_name IS NULL)
        OR (completed_at IS NOT NULL AND result IS NOT NULL AND completed_by IS NOT NULL AND completed_by_name IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

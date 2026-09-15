CREATE TABLE IF NOT EXISTS client_legacy_virtual_accounts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    virtual_account VARCHAR(14) NOT NULL,
    source_content_digest CHAR(64) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_client_legacy_virtual_account_pair (case_no, virtual_account),
    KEY idx_client_legacy_virtual_account_lookup (virtual_account, case_no),
    CONSTRAINT fk_client_legacy_virtual_account_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_legacy_virtual_account_format CHECK (
        virtual_account REGEXP '^99781699[0-9]{6}$'
    ),
    CONSTRAINT chk_client_legacy_virtual_account_source CHECK (
        source_content_digest REGEXP '^[0-9a-f]{64}$' AND source_row >= 2
        AND CHAR_LENGTH(TRIM(created_by)) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

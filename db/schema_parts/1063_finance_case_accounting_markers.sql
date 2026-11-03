-- Application-owned historical accounting marker. No cash or order mutation.
CREATE TABLE IF NOT EXISTS finance_case_accounting_markers (
    case_no VARCHAR(50) COLLATE utf8mb4_bin NOT NULL,
    reason VARCHAR(500) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    source_versions JSON NOT NULL,
    accounting_snapshot JSON NOT NULL,
    operation_key VARCHAR(191) COLLATE utf8mb4_bin NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_no),
    UNIQUE KEY uk_finance_case_marker_operation (operation_key),
    CONSTRAINT chk_finance_case_marker_text CHECK (CHAR_LENGTH(TRIM(reason))>0 AND CHAR_LENGTH(TRIM(actor))>0 AND CHAR_LENGTH(TRIM(operation_key))>0),
    CONSTRAINT chk_finance_case_marker_versions CHECK (JSON_TYPE(source_versions)='OBJECT'),
    CONSTRAINT chk_finance_case_marker_snapshot CHECK (JSON_TYPE(accounting_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

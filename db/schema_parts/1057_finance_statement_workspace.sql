-- Finance Import-owned manual statements, identity-only exclusions and warning acknowledgement.
-- Automatic successful statements remain a read-only projection of committed owner evidence.
CREATE TABLE IF NOT EXISTS finance_statement_archive_state (
    id TINYINT PRIMARY KEY,
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    CONSTRAINT chk_statement_singleton CHECK (id=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT IGNORE INTO finance_statement_archive_state(id,version) VALUES (1,0);

CREATE TABLE IF NOT EXISTS finance_manual_statements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    fields JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_manual_statement_object CHECK (JSON_TYPE(fields)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_statement_commands (
    idempotency_key VARCHAR(191) COLLATE utf8mb4_bin PRIMARY KEY,
    command_digest CHAR(64) NOT NULL,
    result_identity VARCHAR(191) NULL,
    saved_count INT UNSIGNED NOT NULL,
    excluded_count INT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_statement_exclusions (
    finance_import_row_id BIGINT PRIMARY KEY,
    kept_identity VARCHAR(191) COLLATE utf8mb4_bin NOT NULL,
    actor VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_statement_excluded_row FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_accounting_dismissals (
    case_no VARCHAR(50) NOT NULL,
    item_identity VARCHAR(191) COLLATE utf8mb4_bin NOT NULL,
    warning_kind VARCHAR(30) NOT NULL,
    difference_ntd BIGINT NOT NULL,
    source_version VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(case_no,item_identity,warning_kind,difference_ntd),
    CONSTRAINT fk_accounting_dismissal_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

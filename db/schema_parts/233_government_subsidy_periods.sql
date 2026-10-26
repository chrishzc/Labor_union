-- Additive whole-period receipt roots. No claim submission/approval stage or case cash allocation.
CREATE TABLE IF NOT EXISTS client_subsidy_policy_migrations (
    policy_key VARCHAR(100) NOT NULL PRIMARY KEY,
    completed_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_subsidy_identity_label_changes (
    client_id INT NOT NULL PRIMARY KEY,
    before_identity VARCHAR(100) NOT NULL,
    after_identity VARCHAR(100) NOT NULL,
    changed_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_subsidy_identity_client FOREIGN KEY (client_id) REFERENCES clients(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_period_years (
    period_year INT NOT NULL PRIMARY KEY,
    aggregate_version BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_period_entries (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    period_unit VARCHAR(10) NOT NULL,
    period_year INT NOT NULL,
    period_index INT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    amount_ntd BIGINT NOT NULL,
    reversal_of_id BIGINT NULL,
    paid_on DATE NOT NULL,
    idempotency_key VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_subsidy_period_bank (finance_import_row_id),
    UNIQUE KEY uq_subsidy_period_key (idempotency_key),
    UNIQUE KEY uq_subsidy_period_reversal (reversal_of_id),
    KEY ix_subsidy_period_range (period_start,period_end),
    CONSTRAINT fk_subsidy_period_bank FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id),
    CONSTRAINT fk_subsidy_period_reversal FOREIGN KEY (reversal_of_id) REFERENCES government_subsidy_period_entries(id),
    CONSTRAINT ck_subsidy_period_unit CHECK (period_unit IN ('month','quarter','year')),
    CONSTRAINT ck_subsidy_period_amount CHECK (amount_ntd>0),
    CONSTRAINT ck_subsidy_period_range CHECK (period_end>period_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_period_members (
    receipt_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    service_end_date DATE NOT NULL,
    amount_ntd BIGINT NOT NULL,
    PRIMARY KEY (receipt_id,case_no),
    KEY ix_subsidy_period_case (case_no),
    CONSTRAINT fk_subsidy_period_member FOREIGN KEY (receipt_id) REFERENCES government_subsidy_period_entries(id),
    CONSTRAINT ck_subsidy_period_member_amount CHECK (amount_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


INSERT IGNORE INTO client_subsidy_policy_migrations(policy_key) VALUES ('subsidy-period-policy-2026-10-24-v1');

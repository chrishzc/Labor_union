-- Canonical first-use bootstrap for Client Finance, Payroll, and Scheduling.

-- The version is immutable so later rate changes create a new policy identity.
INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'citizen', 300, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'citizen'
);

INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'subsidized_citizen', 350, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'subsidized_citizen'
);

INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'non_citizen', 320, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'non_citizen'
);

CREATE TABLE IF NOT EXISTS case_architecture_bootstrap_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    client_payment_terms_event_id BIGINT NOT NULL,
    client_policy_version VARCHAR(100) NOT NULL,
    client_hourly_rate_ntd BIGINT NOT NULL,
    payroll_policy_version VARCHAR(100) NOT NULL,
    payroll_policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    payroll_hourly_rate_ntd BIGINT NOT NULL,
    source_identity_status VARCHAR(100) NOT NULL,
    candidate_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_architecture_bootstrap_case (case_no),
    UNIQUE KEY uq_case_architecture_bootstrap_idempotency (idempotency_key),
    UNIQUE KEY uq_case_architecture_bootstrap_terms_event (
        client_payment_terms_event_id
    ),
    CONSTRAINT fk_case_architecture_bootstrap_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_architecture_bootstrap_terms_event
        FOREIGN KEY (client_payment_terms_event_id)
        REFERENCES client_payment_terms_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_architecture_bootstrap_payroll_policy
        FOREIGN KEY (payroll_policy_version, payroll_policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_architecture_bootstrap_amounts
        CHECK (
            client_hourly_rate_ntd > 0
            AND payroll_hourly_rate_ntd > 0
        ),
    CONSTRAINT chk_case_architecture_bootstrap_fingerprint
        CHECK (candidate_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_case_architecture_bootstrap_text
        CHECK (
            CHAR_LENGTH(TRIM(source_identity_status)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_payroll_rate_policy_snapshots (
    case_no VARCHAR(50) PRIMARY KEY,
    policy_version VARCHAR(100) NOT NULL,
    policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    source_identity_status VARCHAR(100) NOT NULL,
    source_event_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_payroll_policy_source_event (source_event_id),
    CONSTRAINT fk_case_payroll_policy_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_payroll_policy_definition
        FOREIGN KEY (policy_version, policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_payroll_policy_source_event
        FOREIGN KEY (source_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_payroll_policy_amount
        CHECK (hourly_rate_ntd > 0),
    CONSTRAINT chk_case_payroll_policy_identity
        CHECK (CHAR_LENGTH(TRIM(source_identity_status)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_architecture_bootstrap_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    bootstrap_event_id BIGINT NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    bootstrap_created TINYINT(1) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_architecture_bootstrap_receipt_key (idempotency_key),
    CONSTRAINT fk_case_architecture_bootstrap_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_architecture_bootstrap_receipt_event
        FOREIGN KEY (bootstrap_event_id)
        REFERENCES case_architecture_bootstrap_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_case_architecture_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_case_architecture_receipt_initial_versions
        CHECK (
            client_finance_version = 0
            AND payroll_version = 0
            AND scheduling_version = 0
            AND scheduling_generation = 0
        ),
    CONSTRAINT chk_case_architecture_receipt_created
        CHECK (bootstrap_created IN (0, 1)),
    CONSTRAINT chk_case_architecture_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_events_before_update;
CREATE TRIGGER trg_case_architecture_bootstrap_events_before_update
BEFORE UPDATE ON case_architecture_bootstrap_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_events_before_delete;
CREATE TRIGGER trg_case_architecture_bootstrap_events_before_delete
BEFORE DELETE ON case_architecture_bootstrap_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_payroll_policy_snapshots_before_update;
CREATE TRIGGER trg_case_payroll_policy_snapshots_before_update
BEFORE UPDATE ON case_payroll_rate_policy_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_payroll_policy_snapshots_before_delete;
CREATE TRIGGER trg_case_payroll_policy_snapshots_before_delete
BEFORE DELETE ON case_payroll_rate_policy_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be deleted';

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_receipts_before_update;
CREATE TRIGGER trg_case_architecture_bootstrap_receipts_before_update
BEFORE UPDATE ON case_architecture_bootstrap_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_case_architecture_bootstrap_receipts_before_delete;
CREATE TRIGGER trg_case_architecture_bootstrap_receipts_before_delete
BEFORE DELETE ON case_architecture_bootstrap_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be deleted';

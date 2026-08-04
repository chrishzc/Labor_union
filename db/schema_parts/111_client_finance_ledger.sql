-- Additive Client Finance obligation, immutable ledger, and M:N allocation SSOT.

CREATE TABLE IF NOT EXISTS client_finance_accounts (
    case_no VARCHAR(50) PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_client_finance_account_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_payment_terms_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    client_hourly_rate_ntd BIGINT NOT NULL,
    deposit_service_days INT UNSIGNED NOT NULL,
    deposit_due_date DATE NOT NULL,
    first_payment_due_date DATE NOT NULL,
    second_payment_due_date DATE NULL,
    expected_account_version BIGINT UNSIGNED NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_payment_terms_source (
        case_no,
        source_event_identity
    ),
    UNIQUE KEY uq_client_payment_terms_idempotency (idempotency_key),
    CONSTRAINT fk_client_payment_terms_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_payment_terms_event_values
        CHECK (
            client_hourly_rate_ntd > 0
            AND CHAR_LENGTH(TRIM(policy_version)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_payment_terms (
    case_no VARCHAR(50) PRIMARY KEY,
    policy_version VARCHAR(100) NOT NULL,
    client_hourly_rate_ntd BIGINT NOT NULL,
    deposit_service_days INT UNSIGNED NOT NULL,
    deposit_due_date DATE NOT NULL,
    first_payment_due_date DATE NOT NULL,
    second_payment_due_date DATE NULL,
    current_event_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_payment_terms_current_event (current_event_id),
    CONSTRAINT fk_client_payment_terms_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_payment_terms_current_event
        FOREIGN KEY (current_event_id) REFERENCES client_payment_terms_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_payment_terms_values
        CHECK (
            client_hourly_rate_ntd > 0
            AND CHAR_LENGTH(TRIM(policy_version)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_obligation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    obligation_type ENUM(
        'deposit',
        'first',
        'second',
        'refund',
        'subsidy_return',
        'adjustment'
    ) NOT NULL,
    direction ENUM(
        'receivable_from_client',
        'payable_to_client'
    ) NOT NULL,
    event_type ENUM(
        'established',
        'recalculated',
        'adjusted',
        'reversed'
    ) NOT NULL,
    before_amount_ntd BIGINT NOT NULL,
    after_amount_ntd BIGINT NOT NULL,
    before_due_date DATE NULL,
    after_due_date DATE NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    expected_account_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_obligation_event_idempotency (idempotency_key),
    UNIQUE KEY uq_client_obligation_source_event (
        obligation_identity,
        source_event_identity
    ),
    INDEX idx_client_obligation_event_case_type (
        case_no,
        obligation_type,
        created_at
    ),
    CONSTRAINT fk_client_obligation_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_obligation_event_amount
        CHECK (
            before_amount_ntd >= 0
            AND after_amount_ntd >= 0
            AND (
                before_amount_ntd <> after_amount_ntd
                OR NOT (before_due_date <=> after_due_date)
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_obligations (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    obligation_type ENUM(
        'deposit',
        'first',
        'second',
        'refund',
        'subsidy_return',
        'adjustment'
    ) NOT NULL,
    direction ENUM(
        'receivable_from_client',
        'payable_to_client'
    ) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    amount_due_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    status ENUM('open', 'settled', 'cancelled') NOT NULL,
    current_event_id BIGINT NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_obligation_case_identity (
        obligation_identity,
        case_no
    ),
    INDEX idx_client_obligation_case_status (
        case_no,
        status,
        obligation_type
    ),
    CONSTRAINT fk_client_obligation_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_obligation_current_event
        FOREIGN KEY (current_event_id) REFERENCES client_obligation_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_obligation_amount
        CHECK (amount_due_ntd >= 0),
    CONSTRAINT chk_client_obligation_state
        CHECK (
            (status = 'open' AND amount_due_ntd > 0)
            OR (status IN ('settled', 'cancelled') AND amount_due_ntd = 0)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE client_obligation_events
    ADD CONSTRAINT fk_client_obligation_event_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE client_obligations
    ADD CONSTRAINT fk_client_obligation_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS client_ledger_entries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    finance_import_row_id BIGINT NULL,
    entry_type ENUM(
        'receipt',
        'refund',
        'adjustment',
        'reversal'
    ) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    reconciliation_reference VARCHAR(191) NOT NULL,
    reversal_of_entry_id BIGINT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_ledger_import_row (finance_import_row_id),
    UNIQUE KEY uq_client_ledger_idempotency (idempotency_key),
    INDEX idx_client_ledger_case_date (case_no, occurred_on, id),
    CONSTRAINT fk_client_ledger_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_ledger_import_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_ledger_reversal
        FOREIGN KEY (reversal_of_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_ledger_amount
        CHECK (amount_ntd > 0),
    CONSTRAINT chk_client_ledger_reversal_shape
        CHECK (
            (entry_type = 'reversal' AND reversal_of_entry_id IS NOT NULL)
            OR (entry_type <> 'reversal' AND reversal_of_entry_id IS NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_ledger_obligation_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ledger_entry_id BIGINT NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    allocation_ordinal INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_ledger_obligation_allocation (
        ledger_entry_id,
        obligation_identity
    ),
    UNIQUE KEY uq_client_ledger_allocation_ordinal (
        ledger_entry_id,
        allocation_ordinal
    ),
    INDEX idx_client_allocation_obligation (
        obligation_identity,
        ledger_entry_id
    ),
    CONSTRAINT fk_client_allocation_ledger
        FOREIGN KEY (ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_allocation_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_allocation_amount
        CHECK (amount_ntd > 0),
    CONSTRAINT chk_client_allocation_ordinal
        CHECK (allocation_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_finance_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_finance_receipt_key (idempotency_key),
    CONSTRAINT fk_client_finance_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_finance_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_finance_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_finance_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    intent_type ENUM(
        'orders_deposit_reconciled',
        'orders_deposit_reversed',
        'anomaly_review_required',
        'projection_refresh'
    ) NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_finance_outbox_intent (intent_key),
    INDEX idx_client_finance_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_client_finance_outbox_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_finance_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_obligation_events_before_update;
CREATE TRIGGER trg_client_obligation_events_before_update
BEFORE UPDATE ON client_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_obligation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_obligation_events_before_delete;
CREATE TRIGGER trg_client_obligation_events_before_delete
BEFORE DELETE ON client_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_obligation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_payment_terms_events_before_update;
CREATE TRIGGER trg_client_payment_terms_events_before_update
BEFORE UPDATE ON client_payment_terms_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_payment_terms_events_before_delete;
CREATE TRIGGER trg_client_payment_terms_events_before_delete
BEFORE DELETE ON client_payment_terms_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_ledger_entries_before_update;
CREATE TRIGGER trg_client_ledger_entries_before_update
BEFORE UPDATE ON client_ledger_entries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_ledger_entries_before_delete;
CREATE TRIGGER trg_client_ledger_entries_before_delete
BEFORE DELETE ON client_ledger_entries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_ledger_allocations_before_update;
CREATE TRIGGER trg_client_ledger_allocations_before_update
BEFORE UPDATE ON client_ledger_obligation_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be updated';

DROP TRIGGER IF EXISTS trg_client_ledger_allocations_before_delete;
CREATE TRIGGER trg_client_ledger_allocations_before_delete
BEFORE DELETE ON client_ledger_obligation_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_finance_receipts_before_update;
CREATE TRIGGER trg_client_finance_receipts_before_update
BEFORE UPDATE ON client_finance_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_finance_receipts_before_delete;
CREATE TRIGGER trg_client_finance_receipts_before_delete
BEFORE DELETE ON client_finance_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be deleted';

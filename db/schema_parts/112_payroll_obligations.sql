-- Additive Payroll rate snapshots, special-pay, and staff obligation SSOT.

CREATE TABLE IF NOT EXISTS payroll_case_accounts (
    case_no VARCHAR(50) PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payroll_case_account_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_rate_policies (
    policy_version VARCHAR(100) NOT NULL,
    policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    effective_from DATE NOT NULL,
    effective_until DATE NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (policy_version, policy_kind),
    CONSTRAINT chk_payroll_rate_policy_amount
        CHECK (hourly_rate_ntd > 0),
    CONSTRAINT chk_payroll_rate_policy_interval
        CHECK (
            effective_until IS NULL
            OR effective_until >= effective_from
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS assignment_payroll_rate_snapshots (
    assignment_id BIGINT PRIMARY KEY,
    policy_version VARCHAR(100) NOT NULL,
    policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen'
    ) NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    source_identity_status VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_assignment_payroll_rate_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_payroll_rate_policy
        FOREIGN KEY (policy_version, policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_payroll_rate_amount
        CHECK (hourly_rate_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_special_pay_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    service_date DATE NOT NULL,
    event_type ENUM('double_pay') NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_special_pay_assignment_date (
        assignment_id,
        service_date,
        event_type
    ),
    UNIQUE KEY uq_payroll_special_pay_idempotency (idempotency_key),
    CONSTRAINT fk_payroll_special_pay_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_adjustment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    adjustment_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_adjustment_identity (adjustment_identity),
    UNIQUE KEY uq_payroll_adjustment_idempotency (idempotency_key),
    CONSTRAINT fk_payroll_adjustment_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_adjustment_nonzero
        CHECK (amount_ntd <> 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_adjustment_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    adjustment_event_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    amount_ntd BIGINT NOT NULL,
    allocation_ordinal INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_adjustment_assignment (
        adjustment_event_id,
        assignment_id
    ),
    UNIQUE KEY uq_payroll_adjustment_ordinal (
        adjustment_event_id,
        allocation_ordinal
    ),
    CONSTRAINT fk_payroll_adjustment_allocation_event
        FOREIGN KEY (adjustment_event_id) REFERENCES payroll_adjustment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_adjustment_allocation_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_adjustment_allocation_nonzero
        CHECK (amount_ntd <> 0),
    CONSTRAINT chk_payroll_adjustment_allocation_ordinal
        CHECK (allocation_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_obligation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    assignment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    obligation_kind ENUM(
        'service_pay',
        'adjustment',
        'reversal'
    ) NOT NULL,
    direction ENUM(
        'payable_to_staff',
        'receivable_from_staff'
    ) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    event_type ENUM(
        'established',
        'rebuilt',
        'adjustment',
        'reversal'
    ) NOT NULL,
    before_amount_ntd BIGINT NOT NULL,
    after_amount_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    payroll_fingerprint CHAR(64) NOT NULL,
    expected_payroll_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_obligation_event_idempotency (idempotency_key),
    INDEX idx_staff_obligation_event_identity (
        obligation_identity,
        created_at
    ),
    CONSTRAINT fk_staff_obligation_event_owner
        FOREIGN KEY (assignment_id, case_no, staff_id)
        REFERENCES case_staff_assignments(id, case_no, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_obligation_event_amount
        CHECK (
            before_amount_ntd >= 0
            AND after_amount_ntd >= 0
            AND before_amount_ntd <> after_amount_ntd
        ),
    CONSTRAINT chk_staff_obligation_event_fingerprint
        CHECK (payroll_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_staff_obligation_event_version
        CHECK (resulting_payroll_version = expected_payroll_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_obligations (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    assignment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    obligation_kind ENUM(
        'service_pay',
        'adjustment',
        'reversal'
    ) NOT NULL,
    direction ENUM(
        'payable_to_staff',
        'receivable_from_staff'
    ) NOT NULL,
    source_obligation_identity VARCHAR(191) NULL,
    amount_due_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    status ENUM('open', 'settled', 'cancelled') NOT NULL,
    current_event_id BIGINT NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    payout_history_exists TINYINT(1) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_obligation_case_identity (
        obligation_identity,
        case_no
    ),
    INDEX idx_staff_obligation_assignment (assignment_id),
    INDEX idx_staff_obligation_staff_due (
        staff_id,
        due_date,
        obligation_identity
    ),
    CONSTRAINT fk_staff_obligation_owner
        FOREIGN KEY (assignment_id, case_no, staff_id)
        REFERENCES case_staff_assignments(id, case_no, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_obligation_current_event
        FOREIGN KEY (current_event_id) REFERENCES staff_obligation_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_obligation_state
        CHECK (
            (status = 'open' AND amount_due_ntd > 0)
            OR (
                status IN ('settled', 'cancelled')
                AND amount_due_ntd = 0
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE staff_obligation_events
    ADD CONSTRAINT fk_staff_obligation_event_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES staff_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE staff_obligations
    ADD CONSTRAINT fk_staff_obligation_source
        FOREIGN KEY (source_obligation_identity, case_no)
        REFERENCES staff_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS payroll_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_receipt_idempotency (idempotency_key),
    CONSTRAINT fk_payroll_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_payroll_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'staff_obligation_changed',
        'payroll_anomaly_required'
    ) NOT NULL,
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
    UNIQUE KEY uq_payroll_outbox_intent (intent_key),
    INDEX idx_payroll_outbox_delivery (status, next_attempt_at, id),
    CONSTRAINT fk_payroll_outbox_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_payroll_special_pay_events_before_update;
CREATE TRIGGER trg_payroll_special_pay_events_before_update
BEFORE UPDATE ON payroll_special_pay_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_special_pay_events_before_delete;
CREATE TRIGGER trg_payroll_special_pay_events_before_delete
BEFORE DELETE ON payroll_special_pay_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_events_before_update;
CREATE TRIGGER trg_payroll_adjustment_events_before_update
BEFORE UPDATE ON payroll_adjustment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_events_before_delete;
CREATE TRIGGER trg_payroll_adjustment_events_before_delete
BEFORE DELETE ON payroll_adjustment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_allocations_before_update;
CREATE TRIGGER trg_payroll_adjustment_allocations_before_update
BEFORE UPDATE ON payroll_adjustment_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_adjustment_allocations_before_delete;
CREATE TRIGGER trg_payroll_adjustment_allocations_before_delete
BEFORE DELETE ON payroll_adjustment_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_obligation_events_before_update;
CREATE TRIGGER trg_staff_obligation_events_before_update
BEFORE UPDATE ON staff_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_obligation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_obligation_events_before_delete;
CREATE TRIGGER trg_staff_obligation_events_before_delete
BEFORE DELETE ON staff_obligation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_obligation_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_payroll_apply_receipts_before_update;
CREATE TRIGGER trg_payroll_apply_receipts_before_update
BEFORE UPDATE ON payroll_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_payroll_apply_receipts_before_delete;
CREATE TRIGGER trg_payroll_apply_receipts_before_delete
BEFORE DELETE ON payroll_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be deleted';

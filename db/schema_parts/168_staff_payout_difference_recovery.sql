-- Additive Staff Payables payout-difference projection and recovery root.

ALTER TABLE staff_payable_projections
    MODIFY COLUMN status ENUM(
        'payable', 'partially_paid', 'completed', 'recovery_required', 'anomaly'
    ) NOT NULL;

ALTER TABLE staff_payable_projections
    DROP CHECK chk_staff_payable_projection_status;

ALTER TABLE staff_payable_projections
    ADD CONSTRAINT chk_staff_payable_projection_status
    CHECK (
        (status = 'payable' AND net_paid_ntd = 0 AND balance_ntd = obligation_amount_ntd)
        OR (status = 'partially_paid' AND net_paid_ntd > 0 AND balance_ntd > 0)
        OR (status = 'completed' AND net_paid_ntd = obligation_amount_ntd AND balance_ntd = 0)
        OR (status = 'recovery_required' AND net_paid_ntd = obligation_amount_ntd AND balance_ntd = 0)
        OR (status = 'anomaly' AND balance_ntd < 0)
    );

CREATE TABLE IF NOT EXISTS staff_overpayment_recoveries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    staff_id INT NOT NULL,
    original_amount_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM('open', 'partially_recovered', 'recovered', 'adjusted')
        NOT NULL DEFAULT 'open',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    source_bank_fact_identities JSON NOT NULL,
    source_payout_event_ids JSON NOT NULL,
    source_obligation_identities JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_overpayment_recovery_identity (recovery_identity),
    INDEX idx_staff_overpayment_recovery_staff_status (staff_id, status, id),
    CONSTRAINT fk_staff_overpayment_recovery_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_overpayment_recovery_amount
        CHECK (
            original_amount_ntd > 0
            AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= original_amount_ntd
        ),
    CONSTRAINT chk_staff_overpayment_recovery_sources
        CHECK (
            JSON_TYPE(source_bank_fact_identities) = 'ARRAY'
            AND JSON_TYPE(source_payout_event_ids) = 'ARRAY'
            AND JSON_TYPE(source_obligation_identities) = 'ARRAY'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- This table is the current projection.  Its immutable history is held below,
-- so the recovery workflow may advance remaining/status with an optimistic CAS.
DROP TRIGGER IF EXISTS trg_staff_overpayment_recoveries_before_update;

DROP TRIGGER IF EXISTS trg_staff_overpayment_recoveries_before_delete;
CREATE TRIGGER trg_staff_overpayment_recoveries_before_delete
BEFORE DELETE ON staff_overpayment_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recoveries root facts cannot be deleted';

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    event_type ENUM('cash_recovered', 'authorized_adjustment') NOT NULL,
    finance_import_row_id BIGINT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    resulting_status ENUM('partially_recovered', 'recovered', 'adjusted') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_overpayment_recovery_event_key (idempotency_key),
    UNIQUE KEY uq_staff_overpayment_recovery_event_bank_row (finance_import_row_id),
    CONSTRAINT fk_staff_overpayment_recovery_event_root
        FOREIGN KEY (recovery_identity) REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_overpayment_recovery_event_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_overpayment_recovery_event_amount
        CHECK (before_remaining_ntd > 0 AND after_remaining_ntd >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_overpayment_recovery_receipt_root
        FOREIGN KEY (recovery_identity) REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_overpayment_recovery_events_before_update;
CREATE TRIGGER trg_staff_overpayment_recovery_events_before_update
BEFORE UPDATE ON staff_overpayment_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recovery_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_overpayment_recovery_events_before_delete;
CREATE TRIGGER trg_staff_overpayment_recovery_events_before_delete
BEFORE DELETE ON staff_overpayment_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recovery_events records cannot be deleted';

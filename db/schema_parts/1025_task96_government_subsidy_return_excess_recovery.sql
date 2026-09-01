-- File: 1025_task96_government_subsidy_return_excess_recovery.sql
-- Purpose: add the preserved-data Government Subsidy return-excess owner root.
-- Data effect: schema only; existing return payable, payout, and bank lineage is preserved.

ALTER TABLE government_subsidy_outbox
    MODIFY COLUMN intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_receipt_allocated',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed',
        'government_subsidy_overpayment_established',
        'government_subsidy_overpayment_offset',
        'government_overpayment_return_payable',
        'government_overpayment_return_payout',
        'government_overpayment_return_excess_recovery'
    ) NOT NULL;

ALTER TABLE government_subsidy_overpayment_apply_receipts
    MODIFY COLUMN command_kind ENUM(
        'offset',
        'return',
        'return_reconciliation',
        'return_reconciliation_with_excess'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS government_overpayment_return_excess_recoveries (
    recovery_identity VARCHAR(191) PRIMARY KEY,
    overpayment_identity VARCHAR(191) NOT NULL,
    payable_identity VARCHAR(191) NOT NULL,
    source_finance_import_row_id BIGINT NOT NULL,
    source_payout_id BIGINT NOT NULL,
    payer_identity VARCHAR(191) NOT NULL,
    original_amount_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM('open', 'partially_recovered', 'recovered') NOT NULL DEFAULT 'open',
    projection_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_return_excess_source_payout (source_payout_id),
    UNIQUE KEY uq_government_return_excess_source_bank (source_finance_import_row_id),
    INDEX idx_government_return_excess_status (status, created_at),
    CONSTRAINT fk_government_return_excess_overpayment
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_return_excess_payable
        FOREIGN KEY (payable_identity) REFERENCES government_overpayment_return_payables(payable_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_return_excess_bank
        FOREIGN KEY (source_finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_return_excess_payout
        FOREIGN KEY (source_payout_id) REFERENCES government_overpayment_return_payouts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_return_excess_amount
        CHECK (original_amount_ntd > 0 AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= original_amount_ntd
            AND (remaining_amount_ntd > 0 OR status = 'recovered'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_overpayment_return_excess_recovery_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    event_type ENUM('established', 'incoming_reconciled') NOT NULL,
    finance_import_row_id BIGINT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    resulting_status ENUM('open', 'partially_recovered', 'recovered') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_return_excess_event_key (idempotency_key),
    INDEX idx_government_return_excess_event_root (recovery_identity, id),
    CONSTRAINT fk_government_return_excess_event_root
        FOREIGN KEY (recovery_identity) REFERENCES government_overpayment_return_excess_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_return_excess_event_bank
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_return_excess_event_amount
        CHECK (before_remaining_ntd > 0 AND after_remaining_ntd >= 0
            AND after_remaining_ntd <= before_remaining_ntd
            AND resulting_version = expected_version + 1),
    CONSTRAINT chk_government_return_excess_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_return_excess_recoveries_before_update;
CREATE TRIGGER trg_government_return_excess_recoveries_before_update
BEFORE UPDATE ON government_overpayment_return_excess_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_excess_recoveries records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_return_excess_recoveries_before_delete;
CREATE TRIGGER trg_government_return_excess_recoveries_before_delete
BEFORE DELETE ON government_overpayment_return_excess_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_excess_recoveries records cannot be deleted';

DROP TRIGGER IF EXISTS trg_government_return_excess_events_before_update;
CREATE TRIGGER trg_government_return_excess_events_before_update
BEFORE UPDATE ON government_overpayment_return_excess_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_excess_recovery_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_return_excess_events_before_delete;
CREATE TRIGGER trg_government_return_excess_events_before_delete
BEFORE DELETE ON government_overpayment_return_excess_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_excess_recovery_events records cannot be deleted';

-- Immutable lineage for actual client receipts that exceed one receivable.

CREATE TABLE IF NOT EXISTS client_receipt_overage_dispositions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    receipt_ledger_entry_id BIGINT NOT NULL,
    receivable_obligation_identity VARCHAR(191) NOT NULL,
    refund_obligation_identity VARCHAR(191) NOT NULL,
    overage_amount_ntd BIGINT NOT NULL,
    settlement_identity CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_receipt_overage_bank_row (finance_import_row_id),
    UNIQUE KEY uq_client_receipt_overage_ledger (receipt_ledger_entry_id),
    UNIQUE KEY uq_client_receipt_overage_refund (refund_obligation_identity),
    UNIQUE KEY uq_client_receipt_overage_idempotency (idempotency_key),
    CONSTRAINT fk_client_receipt_overage_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_ledger
        FOREIGN KEY (receipt_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_receivable
        FOREIGN KEY (receivable_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_receipt_overage_refund
        FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_receipt_overage_amount CHECK (overage_amount_ntd > 0),
    CONSTRAINT chk_client_receipt_overage_settlement
        CHECK (settlement_identity REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_receipt_overage_dispositions_before_update;
CREATE TRIGGER trg_client_receipt_overage_dispositions_before_update
BEFORE UPDATE ON client_receipt_overage_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_receipt_overage_dispositions records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_receipt_overage_dispositions_before_delete;
CREATE TRIGGER trg_client_receipt_overage_dispositions_before_delete
BEFORE DELETE ON client_receipt_overage_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_receipt_overage_dispositions records cannot be deleted';

CREATE TABLE IF NOT EXISTS client_over_refund_recoveries (
    recovery_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    refund_ledger_entry_id BIGINT NOT NULL,
    refund_obligation_identity VARCHAR(191) NOT NULL,
    amount_due_ntd BIGINT NOT NULL,
    status ENUM('open', 'settled', 'cancelled') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_bank_row (finance_import_row_id),
    UNIQUE KEY uq_client_over_refund_ledger (refund_ledger_entry_id),
    UNIQUE KEY uq_client_over_refund_idempotency (idempotency_key),
    INDEX idx_client_over_refund_case_status (case_no, status),
    CONSTRAINT fk_client_over_refund_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_ledger
        FOREIGN KEY (refund_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_refund_obligation
        FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_amount CHECK (amount_due_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    event_type ENUM('established', 'collected', 'cancelled') NOT NULL,
    finance_import_row_id BIGINT NULL,
    receipt_ledger_entry_id BIGINT NULL,
    before_amount_ntd BIGINT NOT NULL,
    after_amount_ntd BIGINT NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_event_idempotency (idempotency_key),
    CONSTRAINT fk_client_over_refund_event_recovery
        FOREIGN KEY (recovery_identity) REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_event_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_event_ledger
        FOREIGN KEY (receipt_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_event_amount
        CHECK (
            after_amount_ntd >= 0
            AND (
                (event_type = 'established' AND before_amount_ntd = 0 AND after_amount_ntd > 0)
                OR (event_type IN ('collected', 'cancelled') AND before_amount_ntd > after_amount_ntd)
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_events_before_update;
CREATE TRIGGER trg_client_over_refund_recovery_events_before_update
BEFORE UPDATE ON client_over_refund_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_over_refund_recovery_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_events_before_delete;
CREATE TRIGGER trg_client_over_refund_recovery_events_before_delete
BEFORE DELETE ON client_over_refund_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_over_refund_recovery_events records cannot be deleted';

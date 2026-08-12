-- Canonical incoming-bank settlement for a client refund overpayment recovery.

ALTER TABLE client_over_refund_recoveries
    MODIFY COLUMN status ENUM(
        'open',
        'partially_recovered',
        'recovered',
        'adjusted',
        'settled',
        'cancelled'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    receipt_ledger_entry_id BIGINT NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    resulting_status ENUM('partially_recovered', 'recovered') NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_recovery_receipt_key (idempotency_key),
    UNIQUE KEY uq_client_over_refund_recovery_receipt_bank_row (finance_import_row_id),
    CONSTRAINT fk_client_over_refund_recovery_receipt_recovery
        FOREIGN KEY (recovery_identity)
        REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_recovery_receipt_bank_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_over_refund_recovery_receipt_ledger
        FOREIGN KEY (receipt_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_recovery_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_over_refund_recovery_receipt_remaining
        CHECK (remaining_after_ntd >= 0),
    CONSTRAINT chk_client_over_refund_recovery_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_receipts_before_update;
CREATE TRIGGER trg_client_over_refund_recovery_receipts_before_update
BEFORE UPDATE ON client_over_refund_recovery_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_over_refund_recovery_receipts_before_delete;
CREATE TRIGGER trg_client_over_refund_recovery_receipts_before_delete
BEFORE DELETE ON client_over_refund_recovery_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery receipts cannot be deleted';

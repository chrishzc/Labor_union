-- Durable idempotency receipts for every Government Subsidy overpayment disposition Apply.

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_kind ENUM('offset', 'return', 'return_reconciliation') NOT NULL,
    overpayment_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_apply_receipt_key (idempotency_key),
    CONSTRAINT fk_government_overpayment_apply_receipt_root
        FOREIGN KEY (overpayment_identity)
        REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_apply_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_overpayment_apply_receipts_before_update;
CREATE TRIGGER trg_government_overpayment_apply_receipts_before_update
BEFORE UPDATE ON government_subsidy_overpayment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_overpayment_apply_receipts_before_delete;
CREATE TRIGGER trg_government_overpayment_apply_receipts_before_delete
BEFORE DELETE ON government_subsidy_overpayment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_apply_receipts records cannot be deleted';

-- Append-only idempotency receipt for the canonical deposit reversal command.

CREATE TABLE IF NOT EXISTS client_deposit_reversal_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_deposit_reversal_receipt_key (idempotency_key),
    CONSTRAINT fk_client_deposit_reversal_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_deposit_reversal_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_deposit_reversal_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_deposit_reversal_receipts_before_update;
CREATE TRIGGER trg_client_deposit_reversal_receipts_before_update
BEFORE UPDATE ON client_deposit_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_deposit_reversal_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_client_deposit_reversal_receipts_before_delete;
CREATE TRIGGER trg_client_deposit_reversal_receipts_before_delete
BEFORE DELETE ON client_deposit_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_deposit_reversal_apply_receipts records cannot be deleted';

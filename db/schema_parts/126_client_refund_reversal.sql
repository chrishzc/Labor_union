-- Additive idempotency receipt SSOT for Client Refund and Client Reversal.

CREATE TABLE IF NOT EXISTS client_refund_reversal_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    correction_type ENUM('refund', 'reversal') NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_reversal_receipt_key (idempotency_key),
    INDEX idx_client_refund_reversal_case (
        case_no,
        correction_type,
        created_at
    ),
    CONSTRAINT fk_client_refund_reversal_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_reversal_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_refund_reversal_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_reversal_receipt_before_update;
CREATE TRIGGER trg_client_refund_reversal_receipt_before_update
BEFORE UPDATE ON client_refund_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_reversal_receipt_before_delete;
CREATE TRIGGER trg_client_refund_reversal_receipt_before_delete
BEFORE DELETE ON client_refund_reversal_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be deleted';

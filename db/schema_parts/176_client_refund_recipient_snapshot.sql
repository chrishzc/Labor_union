-- Immutable recipient account selected when a client refund payable is created.
CREATE TABLE IF NOT EXISTS client_refund_recipient_snapshots (
    refund_obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    bank_code VARCHAR(50) NOT NULL,
    bank_account VARCHAR(191) NOT NULL,
    source_kind VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_client_refund_snapshot_obligation
        FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_snapshot_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_snapshot_account
        CHECK (CHAR_LENGTH(TRIM(bank_code)) > 0 AND CHAR_LENGTH(TRIM(bank_account)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_recipient_snapshots_before_update;
CREATE TRIGGER trg_client_refund_recipient_snapshots_before_update
BEFORE UPDATE ON client_refund_recipient_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund recipient snapshots cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_recipient_snapshots_before_delete;
CREATE TRIGGER trg_client_refund_recipient_snapshots_before_delete
BEFORE DELETE ON client_refund_recipient_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund recipient snapshots cannot be deleted';

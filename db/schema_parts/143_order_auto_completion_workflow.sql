-- Append-only receipt for the canonical Orders service auto-completion command.

CREATE TABLE IF NOT EXISTS order_auto_completion_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    completion_instant DATETIME NOT NULL,
    evaluation_at DATETIME NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_auto_completion_receipt_key (idempotency_key),
    UNIQUE KEY uq_order_auto_completion_lifecycle_event (lifecycle_event_id),
    CONSTRAINT fk_order_auto_completion_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_auto_completion_receipt_lifecycle_event
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_auto_completion_receipt_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_auto_completion_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_auto_completion_receipts_before_update;
CREATE TRIGGER trg_order_auto_completion_receipts_before_update
BEFORE UPDATE ON order_auto_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_auto_completion_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_auto_completion_receipts_before_delete;
CREATE TRIGGER trg_order_auto_completion_receipts_before_delete
BEFORE DELETE ON order_auto_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_auto_completion_apply_receipts records cannot be deleted';

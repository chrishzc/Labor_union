-- Additive immutable receipt for the Orders contract-completion workflow.

CREATE TABLE IF NOT EXISTS order_contract_completion_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    contract_event_id BIGINT NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    contract_identity VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_contract_completion_receipt_key (idempotency_key),
    CONSTRAINT fk_order_contract_completion_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_contract_completion_receipt_contract_event
        FOREIGN KEY (contract_event_id)
        REFERENCES order_contract_flow_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_contract_completion_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_contract_completion_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_contract_completion_receipt_text
        CHECK (
            CHAR_LENGTH(TRIM(contract_identity)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        ),
    CONSTRAINT chk_order_contract_completion_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_contract_completion_receipts_before_update;
CREATE TRIGGER trg_order_contract_completion_receipts_before_update
BEFORE UPDATE ON order_contract_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_order_contract_completion_receipts_before_delete;
CREATE TRIGGER trg_order_contract_completion_receipts_before_delete
BEFORE DELETE ON order_contract_completion_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be deleted';

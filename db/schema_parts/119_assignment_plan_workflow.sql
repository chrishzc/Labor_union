-- Append-only receipt for one cross-Domain Assignment Plan Apply.

CREATE TABLE IF NOT EXISTS assignment_plan_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_number INT UNSIGNED NOT NULL,
    expected_client_finance_version BIGINT UNSIGNED NOT NULL,
    resulting_client_finance_version BIGINT UNSIGNED NOT NULL,
    expected_payroll_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    scheduling_receipt_id BIGINT NOT NULL,
    cancelled_assignment_ids JSON NOT NULL,
    created_assignment_keys JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_assignment_plan_receipt_key (idempotency_key),
    CONSTRAINT fk_assignment_plan_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_plan_scheduling_receipt
        FOREIGN KEY (scheduling_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_plan_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_assignment_plan_receipt_versions
        CHECK (
            resulting_order_version = expected_order_version + 1
            AND resulting_scheduling_version =
                expected_scheduling_version + 1
            AND resulting_client_finance_version =
                expected_client_finance_version + 1
            AND resulting_payroll_version = expected_payroll_version + 1
        ),
    CONSTRAINT chk_assignment_plan_receipt_arrays
        CHECK (
            JSON_TYPE(cancelled_assignment_ids) = 'ARRAY'
            AND JSON_TYPE(created_assignment_keys) = 'ARRAY'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_assignment_plan_receipts_before_update;
CREATE TRIGGER trg_assignment_plan_receipts_before_update
BEFORE UPDATE ON assignment_plan_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_assignment_plan_receipts_before_delete;
CREATE TRIGGER trg_assignment_plan_receipts_before_delete
BEFORE DELETE ON assignment_plan_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be deleted';

-- Additive cross-domain financial adjustment SSOT and idempotency receipts.

CREATE TABLE IF NOT EXISTS financial_adjustments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    adjustment_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    adjustment_source_type ENUM(
        'preview_recalculation',
        'manual_extra'
    ) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    amount_delta_ntd BIGINT NOT NULL,
    reason VARCHAR(255) NULL,
    reversal_of_adjustment_id BIGINT NULL,
    cancelled_at TIMESTAMP NULL,
    apply_idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_financial_adjustment_identity (adjustment_identity),
    UNIQUE KEY uq_financial_adjustment_apply_key (apply_idempotency_key),
    UNIQUE KEY uq_financial_adjustment_source (
        case_no,
        source_event_identity
    ),
    INDEX idx_financial_adjustment_case_created (
        case_no,
        created_at,
        id
    ),
    CONSTRAINT fk_financial_adjustment_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_financial_adjustment_reversal
        FOREIGN KEY (reversal_of_adjustment_id)
        REFERENCES financial_adjustments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_financial_adjustment_amount
        CHECK (amount_delta_ntd <> 0),
    CONSTRAINT chk_financial_adjustment_reason
        CHECK (
            (
                adjustment_source_type = 'manual_extra'
                AND reason IS NOT NULL
                AND CHAR_LENGTH(TRIM(reason)) > 0
            )
            OR (
                adjustment_source_type = 'preview_recalculation'
                AND reason IS NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_adjustment_staff_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    financial_adjustment_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    amount_delta_ntd BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_financial_adjustment_staff_assignment (
        financial_adjustment_id,
        assignment_id
    ),
    INDEX idx_financial_adjustment_staff_assignment (
        assignment_id,
        financial_adjustment_id
    ),
    CONSTRAINT fk_financial_adjustment_staff_parent
        FOREIGN KEY (financial_adjustment_id)
        REFERENCES financial_adjustments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_financial_adjustment_staff_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_financial_adjustment_staff_amount
        CHECK (amount_delta_ntd <> 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS financial_adjustment_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    resulting_client_account_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_financial_adjustment_receipt_key (idempotency_key),
    CONSTRAINT fk_financial_adjustment_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_financial_adjustment_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_financial_adjustment_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_financial_adjustments_before_update;
CREATE TRIGGER trg_financial_adjustments_before_update
BEFORE UPDATE ON financial_adjustments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be updated';

DROP TRIGGER IF EXISTS trg_financial_adjustments_before_delete;
CREATE TRIGGER trg_financial_adjustments_before_delete
BEFORE DELETE ON financial_adjustments
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be deleted';

DROP TRIGGER IF EXISTS trg_financial_adjustment_staff_before_update;
CREATE TRIGGER trg_financial_adjustment_staff_before_update
BEFORE UPDATE ON financial_adjustment_staff_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be updated';

DROP TRIGGER IF EXISTS trg_financial_adjustment_staff_before_delete;
CREATE TRIGGER trg_financial_adjustment_staff_before_delete
BEFORE DELETE ON financial_adjustment_staff_allocations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be deleted';

DROP TRIGGER IF EXISTS trg_financial_adjustment_receipt_before_update;
CREATE TRIGGER trg_financial_adjustment_receipt_before_update
BEFORE UPDATE ON financial_adjustment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_financial_adjustment_receipt_before_delete;
CREATE TRIGGER trg_financial_adjustment_receipt_before_delete
BEFORE DELETE ON financial_adjustment_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be deleted';

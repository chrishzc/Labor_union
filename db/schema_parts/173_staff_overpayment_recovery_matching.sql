-- Immutable staff return matching; canonical bank facts retain no recovery target.

ALTER TABLE staff_payables_outbox
    MODIFY COLUMN intent_type ENUM(
        'payable_projection_refresh',
        'payout_anomaly_required',
        'staff_overpayment_recovery_updated',
        'staff_overpayment_recovery_matched',
        'staff_overpayment_recovery_collected'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_matchings (
    matching_identity VARCHAR(191) PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    staff_id INT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    recovery_version BIGINT UNSIGNED NOT NULL,
    staff_payables_version BIGINT UNSIGNED NOT NULL,
    matching_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_recovery_matching_bank_row (finance_import_row_id),
    UNIQUE KEY uq_staff_recovery_matching_idempotency (idempotency_key),
    CONSTRAINT fk_staff_recovery_matching_root FOREIGN KEY (recovery_identity)
        REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_recovery_matching_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_recovery_matching_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_recovery_matching_version CHECK (matching_version = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_overpayment_recovery_matching_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    matching_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_recovery_matching_receipt FOREIGN KEY (matching_identity)
        REFERENCES staff_overpayment_recovery_matchings(matching_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_recovery_matching_receipt_fingerprint CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_staff_recovery_matching_receipt_snapshot CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_recovery_matchings_before_update;
CREATE TRIGGER trg_staff_recovery_matchings_before_update
BEFORE UPDATE ON staff_overpayment_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff overpayment recovery matchings cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_recovery_matchings_before_delete;
CREATE TRIGGER trg_staff_recovery_matchings_before_delete
BEFORE DELETE ON staff_overpayment_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff overpayment recovery matchings cannot be deleted';

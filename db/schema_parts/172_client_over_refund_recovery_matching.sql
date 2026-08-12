-- Immutable human-confirmed matching; finance_import_rows remain canonical bank facts.

ALTER TABLE client_finance_outbox
    MODIFY COLUMN intent_type ENUM(
        'orders_deposit_reconciled',
        'orders_deposit_reversed',
        'anomaly_review_required',
        'projection_refresh',
        'client_over_refund_recovery_matched',
        'client_over_refund_recovery_collected'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_matchings (
    matching_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    recovery_version BIGINT UNSIGNED NOT NULL,
    account_version BIGINT UNSIGNED NOT NULL,
    matching_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_recovery_matching_bank_row (finance_import_row_id),
    UNIQUE KEY uq_client_recovery_matching_idempotency (idempotency_key),
    INDEX idx_client_recovery_matching_recovery (recovery_identity, matching_version),
    CONSTRAINT fk_client_recovery_matching_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_recovery_matching_recovery FOREIGN KEY (recovery_identity)
        REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_recovery_matching_bank_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_recovery_matching_version CHECK (matching_version = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_matching_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    matching_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_recovery_matching_receipt_key (idempotency_key),
    CONSTRAINT fk_client_recovery_matching_receipt FOREIGN KEY (matching_identity)
        REFERENCES client_over_refund_recovery_matchings(matching_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_recovery_matching_receipt_fingerprint CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_client_recovery_matching_receipt_snapshot CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_recovery_matchings_before_update;
CREATE TRIGGER trg_client_recovery_matchings_before_update
BEFORE UPDATE ON client_over_refund_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matchings cannot be updated';

DROP TRIGGER IF EXISTS trg_client_recovery_matchings_before_delete;
CREATE TRIGGER trg_client_recovery_matchings_before_delete
BEFORE DELETE ON client_over_refund_recovery_matchings
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matchings cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_recovery_matching_receipts_before_update;
CREATE TRIGGER trg_client_recovery_matching_receipts_before_update
BEFORE UPDATE ON client_over_refund_recovery_matching_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matching receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_recovery_matching_receipts_before_delete;
CREATE TRIGGER trg_client_recovery_matching_receipts_before_delete
BEFORE DELETE ON client_over_refund_recovery_matching_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matching receipts cannot be deleted';

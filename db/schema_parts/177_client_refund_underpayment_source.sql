ALTER TABLE client_finance_outbox
    MODIFY COLUMN intent_type ENUM(
        'orders_deposit_reconciled',
        'orders_deposit_reversed',
        'anomaly_review_required',
        'projection_refresh',
        'client_over_refund_recovery_matched',
        'client_over_refund_recovery_collected',
        'client_refund_underpayment_required'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_refund_underpayment_sources (
    underpayment_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    bank_total_ntd BIGINT NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_refund_underpayment_idempotency (idempotency_key),
    CONSTRAINT fk_client_refund_underpayment_order FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_underpayment_amount CHECK (bank_total_ntd > 0 AND remaining_after_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_refund_underpayment_source_bank_rows (
    underpayment_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    ordinal INT NOT NULL,
    PRIMARY KEY (underpayment_identity, finance_import_row_id),
    UNIQUE KEY uq_client_refund_underpayment_consumed_row (finance_import_row_id),
    CONSTRAINT fk_client_refund_underpayment_row_source FOREIGN KEY (underpayment_identity) REFERENCES client_refund_underpayment_sources(underpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_underpayment_row FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_underpayment_row_ordinal CHECK (ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_refund_underpayment_source_obligations (
    underpayment_identity VARCHAR(191) NOT NULL,
    refund_obligation_identity VARCHAR(191) NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    PRIMARY KEY (underpayment_identity, refund_obligation_identity),
    CONSTRAINT fk_client_refund_underpayment_obligation_source FOREIGN KEY (underpayment_identity) REFERENCES client_refund_underpayment_sources(underpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_refund_underpayment_obligation FOREIGN KEY (refund_obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_refund_underpayment_obligation_remaining CHECK (remaining_after_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_sources_before_update;
CREATE TRIGGER trg_client_refund_underpayment_sources_before_update
BEFORE UPDATE ON client_refund_underpayment_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment sources cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_sources_before_delete;
CREATE TRIGGER trg_client_refund_underpayment_sources_before_delete
BEFORE DELETE ON client_refund_underpayment_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment sources cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_rows_before_update;
CREATE TRIGGER trg_client_refund_underpayment_source_rows_before_update
BEFORE UPDATE ON client_refund_underpayment_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source bank rows cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_rows_before_delete;
CREATE TRIGGER trg_client_refund_underpayment_source_rows_before_delete
BEFORE DELETE ON client_refund_underpayment_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source bank rows cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_obligations_before_update;
CREATE TRIGGER trg_client_refund_underpayment_source_obligations_before_update
BEFORE UPDATE ON client_refund_underpayment_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source obligations cannot be updated';

DROP TRIGGER IF EXISTS trg_client_refund_underpayment_source_obligations_before_delete;
CREATE TRIGGER trg_client_refund_underpayment_source_obligations_before_delete
BEFORE DELETE ON client_refund_underpayment_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source obligations cannot be deleted';

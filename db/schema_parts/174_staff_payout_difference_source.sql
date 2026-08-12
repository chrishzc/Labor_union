-- Immutable multi-bank source for a Staff Payables payout-difference action.

CREATE TABLE IF NOT EXISTS staff_payout_difference_sources (
    payout_difference_identity VARCHAR(191) PRIMARY KEY,
    staff_id INT NOT NULL,
    difference_mode ENUM('underpayment','overpayment') NOT NULL,
    bank_total_ntd BIGINT NOT NULL,
    obligation_total_ntd BIGINT NOT NULL,
    recovery_identity VARCHAR(191) NULL,
    resulting_staff_payables_version BIGINT UNSIGNED NOT NULL,
    source_bank_facts_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payout_difference_source_key (idempotency_key),
    CONSTRAINT fk_staff_payout_difference_source_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_difference_source_recovery FOREIGN KEY (recovery_identity)
        REFERENCES staff_overpayment_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payout_difference_source_amounts CHECK (
        bank_total_ntd > 0 AND obligation_total_ntd > 0
        AND ((difference_mode = 'underpayment' AND bank_total_ntd < obligation_total_ntd)
          OR (difference_mode = 'overpayment' AND bank_total_ntd > obligation_total_ntd))
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payout_difference_source_bank_rows (
    payout_difference_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    PRIMARY KEY (payout_difference_identity, finance_import_row_id),
    UNIQUE KEY uq_staff_payout_difference_source_bank_ordinal (payout_difference_identity, ordinal),
    CONSTRAINT fk_staff_payout_difference_source_bank_root FOREIGN KEY (payout_difference_identity)
        REFERENCES staff_payout_difference_sources(payout_difference_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_difference_source_bank_row FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payout_difference_source_obligations (
    payout_difference_identity VARCHAR(191) NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    PRIMARY KEY (payout_difference_identity, obligation_identity),
    UNIQUE KEY uq_staff_payout_difference_source_obligation_ordinal (payout_difference_identity, ordinal),
    CONSTRAINT fk_staff_payout_difference_source_obligation_root FOREIGN KEY (payout_difference_identity)
        REFERENCES staff_payout_difference_sources(payout_difference_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_difference_source_obligation FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_payout_difference_sources_before_update;
CREATE TRIGGER trg_staff_payout_difference_sources_before_update
BEFORE UPDATE ON staff_payout_difference_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference sources cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_sources_before_delete;
CREATE TRIGGER trg_staff_payout_difference_sources_before_delete
BEFORE DELETE ON staff_payout_difference_sources
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference sources cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_rows_before_update;
CREATE TRIGGER trg_staff_payout_difference_source_rows_before_update
BEFORE UPDATE ON staff_payout_difference_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source bank rows cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_rows_before_delete;
CREATE TRIGGER trg_staff_payout_difference_source_rows_before_delete
BEFORE DELETE ON staff_payout_difference_source_bank_rows
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source bank rows cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_obligations_before_update;
CREATE TRIGGER trg_staff_payout_difference_source_obligations_before_update
BEFORE UPDATE ON staff_payout_difference_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source obligations cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_difference_source_obligations_before_delete;
CREATE TRIGGER trg_staff_payout_difference_source_obligations_before_delete
BEFORE DELETE ON staff_payout_difference_source_obligations
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source obligations cannot be deleted';

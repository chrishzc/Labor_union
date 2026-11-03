-- Owning-domain noncash dispositions, manual amount modes and frozen government periods.

CREATE TABLE IF NOT EXISTS client_finance_amount_controls (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    amount_mode ENUM('automatic','manual') NOT NULL,
    computed_ntd BIGINT NOT NULL,
    effective_ntd BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_client_finance_amount_source FOREIGN KEY (obligation_identity) REFERENCES client_obligations(obligation_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_finance_amount_control CHECK(computed_ntd>=0 AND effective_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_finance_amount_changes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    action ENUM('manual_amount','adopt_calculation','source_update') NOT NULL,
    before_ntd BIGINT NOT NULL,
    after_ntd BIGINT NOT NULL,
    computed_ntd BIGINT NOT NULL,
    operation_key VARCHAR(191) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    confirmed_on DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_finance_amount_key(operation_key),
    INDEX ix_client_finance_amount_history(obligation_identity,id),
    CONSTRAINT fk_client_finance_amount_change_source FOREIGN KEY (obligation_identity) REFERENCES client_obligations(obligation_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_finance_amount_change CHECK(before_ntd>=0 AND after_ntd>=0 AND computed_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_amount_controls (
    settlement_base_ntd BIGINT NULL,
    obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    amount_mode ENUM('automatic','manual') NOT NULL,
    computed_ntd BIGINT NOT NULL,
    effective_ntd BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payroll_amount_source FOREIGN KEY (obligation_identity) REFERENCES staff_obligations(obligation_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_amount_control CHECK(computed_ntd>=0 AND effective_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_amount_changes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    action ENUM('manual_amount','adopt_calculation','source_update') NOT NULL,
    before_ntd BIGINT NOT NULL,
    after_ntd BIGINT NOT NULL,
    computed_ntd BIGINT NOT NULL,
    operation_key VARCHAR(191) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    confirmed_on DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_amount_key(operation_key),
    INDEX ix_payroll_amount_history(obligation_identity,id),
    CONSTRAINT fk_payroll_amount_change_source FOREIGN KEY (obligation_identity) REFERENCES staff_obligations(obligation_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_amount_change CHECK(before_ntd>=0 AND after_ntd>=0 AND computed_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_amount_controls (
    case_no VARCHAR(50) PRIMARY KEY,
    period_year SMALLINT UNSIGNED NOT NULL,
    amount_mode ENUM('automatic','manual') NOT NULL,
    computed_ntd BIGINT NOT NULL,
    effective_ntd BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_government_subsidy_amount_source FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_amount_control CHECK(computed_ntd>=0 AND effective_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_amount_changes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    action ENUM('manual_amount','adopt_calculation','source_update') NOT NULL,
    before_ntd BIGINT NOT NULL,
    after_ntd BIGINT NOT NULL,
    computed_ntd BIGINT NOT NULL,
    operation_key VARCHAR(191) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    confirmed_on DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_amount_key(operation_key),
    INDEX ix_government_subsidy_amount_history(case_no,id),
    CONSTRAINT fk_government_subsidy_amount_change_source FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_amount_change CHECK(before_ntd>=0 AND after_ntd>=0 AND computed_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_finance_noncash_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    target_identity VARCHAR(191) NOT NULL,
    target_kind ENUM('obligation','over_refund_recovery') NOT NULL,
    action ENUM('loss','reduce_service_fee','union_bank_fee','absorb_overpayment') NOT NULL,
    original_ntd BIGINT NOT NULL,
    amount_ntd BIGINT NOT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    bank_fee_row_id BIGINT NULL,
    operation_key VARCHAR(191) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    confirmed_on DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_noncash_key(operation_key),
    UNIQUE KEY uq_client_noncash_bank_fee(bank_fee_row_id),
    INDEX ix_client_noncash_target(target_identity,id),
    CONSTRAINT fk_client_noncash_case FOREIGN KEY(case_no) REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_noncash_fee FOREIGN KEY(bank_fee_row_id) REFERENCES finance_import_rows(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_noncash_amount CHECK(original_ntd>=0 AND amount_ntd>0 AND before_remaining_ntd>=amount_ntd AND after_remaining_ntd=before_remaining_ntd-amount_ntd),
    CONSTRAINT chk_client_noncash_reason CHECK(CHAR_LENGTH(TRIM(reason))>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_recovery_noncash_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    action ENUM('loss','absorb_overpayment') NOT NULL,
    amount_ntd BIGINT NOT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    operation_key VARCHAR(191) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    confirmed_on DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_noncash_key(operation_key),
    INDEX ix_staff_noncash_recovery(recovery_identity,id),
    CONSTRAINT fk_staff_noncash_recovery FOREIGN KEY(recovery_identity) REFERENCES staff_overpayment_recoveries(recovery_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_noncash_amount CHECK(amount_ntd>0 AND before_remaining_ntd>=amount_ntd AND after_remaining_ntd=before_remaining_ntd-amount_ntd),
    CONSTRAINT chk_staff_noncash_reason CHECK(CHAR_LENGTH(TRIM(reason))>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_period_balances (
    balance_identity VARCHAR(191) PRIMARY KEY,
    root_receipt_id BIGINT NOT NULL,
    balance_kind ENUM('original','correction') NOT NULL,
    case_no VARCHAR(50) NULL,
    direction ENUM('receivable','payable') NOT NULL,
    expected_ntd BIGINT NOT NULL,
    received_ntd BIGINT NOT NULL DEFAULT 0,
    recognized_ntd BIGINT NOT NULL DEFAULT 0,
    returned_ntd BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_government_balance_receipt FOREIGN KEY(root_receipt_id) REFERENCES government_subsidy_period_entries(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_balance_case FOREIGN KEY(case_no) REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_balance_amount CHECK(expected_ntd>=0 AND received_ntd>=0 AND recognized_ntd>=0 AND returned_ntd>=0),
    INDEX ix_government_balance_kind(root_receipt_id,balance_kind,case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_period_operations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    balance_identity VARCHAR(191) NOT NULL,
    action ENUM('receipt','refund','loss','absorb_overpayment','correction') NOT NULL,
    amount_ntd BIGINT NOT NULL,
    bank_entry_id BIGINT NULL,
    operation_key VARCHAR(191) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    confirmed_on DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_operation_key(operation_key),
    UNIQUE KEY uq_government_operation_bank(bank_entry_id),
    INDEX ix_government_operation_balance(balance_identity,id),
    CONSTRAINT fk_government_operation_balance FOREIGN KEY(balance_identity) REFERENCES government_subsidy_period_balances(balance_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_operation_bank FOREIGN KEY(bank_entry_id) REFERENCES government_subsidy_period_entries(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_operation_amount CHECK(amount_ntd>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_finance_amount_changes_update;
CREATE TRIGGER trg_client_finance_amount_changes_update BEFORE UPDATE ON client_finance_amount_changes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_finance_amount_changes is immutable';

DROP TRIGGER IF EXISTS trg_client_finance_amount_changes_delete;
CREATE TRIGGER trg_client_finance_amount_changes_delete BEFORE DELETE ON client_finance_amount_changes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_finance_amount_changes is immutable';

DROP TRIGGER IF EXISTS trg_payroll_amount_changes_update;
CREATE TRIGGER trg_payroll_amount_changes_update BEFORE UPDATE ON payroll_amount_changes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'payroll_amount_changes is immutable';

DROP TRIGGER IF EXISTS trg_payroll_amount_changes_delete;
CREATE TRIGGER trg_payroll_amount_changes_delete BEFORE DELETE ON payroll_amount_changes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'payroll_amount_changes is immutable';

DROP TRIGGER IF EXISTS trg_government_subsidy_amount_changes_update;
CREATE TRIGGER trg_government_subsidy_amount_changes_update BEFORE UPDATE ON government_subsidy_amount_changes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'government_subsidy_amount_changes is immutable';

DROP TRIGGER IF EXISTS trg_government_subsidy_amount_changes_delete;
CREATE TRIGGER trg_government_subsidy_amount_changes_delete BEFORE DELETE ON government_subsidy_amount_changes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'government_subsidy_amount_changes is immutable';

DROP TRIGGER IF EXISTS trg_client_finance_noncash_events_update;
CREATE TRIGGER trg_client_finance_noncash_events_update BEFORE UPDATE ON client_finance_noncash_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_finance_noncash_events is immutable';

DROP TRIGGER IF EXISTS trg_client_finance_noncash_events_delete;
CREATE TRIGGER trg_client_finance_noncash_events_delete BEFORE DELETE ON client_finance_noncash_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_finance_noncash_events is immutable';

DROP TRIGGER IF EXISTS trg_staff_recovery_noncash_events_update;
CREATE TRIGGER trg_staff_recovery_noncash_events_update BEFORE UPDATE ON staff_recovery_noncash_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff_recovery_noncash_events is immutable';

DROP TRIGGER IF EXISTS trg_staff_recovery_noncash_events_delete;
CREATE TRIGGER trg_staff_recovery_noncash_events_delete BEFORE DELETE ON staff_recovery_noncash_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff_recovery_noncash_events is immutable';

DROP TRIGGER IF EXISTS trg_government_subsidy_period_operations_update;
CREATE TRIGGER trg_government_subsidy_period_operations_update BEFORE UPDATE ON government_subsidy_period_operations FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'government_subsidy_period_operations is immutable';

DROP TRIGGER IF EXISTS trg_government_subsidy_period_operations_delete;
CREATE TRIGGER trg_government_subsidy_period_operations_delete BEFORE DELETE ON government_subsidy_period_operations FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'government_subsidy_period_operations is immutable';

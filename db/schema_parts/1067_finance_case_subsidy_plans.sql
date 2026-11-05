-- Independent human subsidy plans; no collection gate and no financial data rewrite.
CREATE TABLE IF NOT EXISTS finance_case_subsidy_plan_events (
    case_no VARCHAR(50) COLLATE utf8mb4_bin NOT NULL,
    version BIGINT NOT NULL,
    scheme ENUM('split','advance','direct') NOT NULL,
    actor VARCHAR(100) NOT NULL,
    operation_key VARCHAR(191) COLLATE utf8mb4_bin NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_no,version),
    UNIQUE KEY uk_finance_subsidy_plan_operation (operation_key),
    CONSTRAINT chk_finance_subsidy_plan_version CHECK (version>0),
    CONSTRAINT chk_finance_subsidy_plan_text CHECK (CHAR_LENGTH(TRIM(actor))>0 AND CHAR_LENGTH(TRIM(operation_key))>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_finance_case_subsidy_plan_events_update;
CREATE TRIGGER trg_finance_case_subsidy_plan_events_update BEFORE UPDATE ON finance_case_subsidy_plan_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'finance_case_subsidy_plan_events is immutable';

DROP TRIGGER IF EXISTS trg_finance_case_subsidy_plan_events_delete;
CREATE TRIGGER trg_finance_case_subsidy_plan_events_delete BEFORE DELETE ON finance_case_subsidy_plan_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'finance_case_subsidy_plan_events is immutable';

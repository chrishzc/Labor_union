-- File: 222_matching_plan_create_receipts.sql
-- Description: Scheduling-owned immutable receipts for formal matching-plan create commands.
-- Data effect: schema_only; no historical plan or segment is backfilled into a receipt.

CREATE TABLE IF NOT EXISTS matching_plan_create_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    plan_id BIGINT NOT NULL,
    plan_version INT UNSIGNED NOT NULL,
    plan_status ENUM('proposed') NOT NULL,
    actor VARCHAR(191) NOT NULL,
    as_of DATE NOT NULL,
    result_kind ENUM('created', 'existing') NOT NULL,
    ordered_segments JSON NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_plan_create_receipt_key (idempotency_key),
    INDEX idx_matching_plan_create_receipt_case (case_no, plan_id),
    CONSTRAINT fk_matching_plan_create_receipt_case FOREIGN KEY (case_no)
        REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_plan_create_receipt_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_plan_create_receipt_fingerprint CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_plan_create_receipt_actor CHECK (
        CHAR_LENGTH(TRIM(actor)) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_matching_plan_create_receipts_before_update;
CREATE TRIGGER trg_matching_plan_create_receipts_before_update
BEFORE UPDATE ON matching_plan_create_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching plan create receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_matching_plan_create_receipts_before_delete;
CREATE TRIGGER trg_matching_plan_create_receipts_before_delete
BEFORE DELETE ON matching_plan_create_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching plan create receipts cannot be deleted';

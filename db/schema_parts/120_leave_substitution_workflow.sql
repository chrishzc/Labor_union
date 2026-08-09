-- Typed leave/substitution batch, immutable outcomes, occupancy, and receipt.

CREATE TABLE IF NOT EXISTS scheduling_leave_substitution_batches (
    batch_key VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    original_assignment_id BIGINT NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    item_count INT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    request_snapshot JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_key),
    INDEX idx_scheduling_leave_batch_case_time (case_no, created_at),
    CONSTRAINT fk_scheduling_leave_batch_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_batch_original_assignment
        FOREIGN KEY (original_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_batch_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND request_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_scheduling_leave_batch_identity
        CHECK (
            item_count > 0
            AND CHAR_LENGTH(TRIM(batch_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND JSON_TYPE(request_snapshot) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_leave_substitution_outcomes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_key VARCHAR(191) NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    original_assignment_id BIGINT NOT NULL,
    original_schedule_id INT NOT NULL,
    original_staff_id INT NOT NULL,
    original_work_date DATE NOT NULL,
    resolution_type ENUM(
        'defer_following_assignments',
        'substitute'
    ) NOT NULL,
    leave_occupancy_date DATE NOT NULL,
    resulting_assignment_id BIGINT NOT NULL,
    resulting_staff_id INT NOT NULL,
    resulting_service_date DATE NOT NULL,
    is_double_pay BOOLEAN NOT NULL DEFAULT FALSE,
    result_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    outcome_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_leave_outcome_ordinal (batch_key, item_index),
    UNIQUE KEY uq_scheduling_leave_outcome_event_key (event_key),
    UNIQUE KEY uq_scheduling_leave_outcome_identity (id, batch_key),
    CONSTRAINT fk_scheduling_leave_outcome_batch
        FOREIGN KEY (batch_key)
        REFERENCES scheduling_leave_substitution_batches(batch_key)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_outcome_original_assignment
        FOREIGN KEY (original_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_outcome_original_schedule
        FOREIGN KEY (original_schedule_id) REFERENCES staff_schedule(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_outcome_resulting_assignment
        FOREIGN KEY (resulting_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_outcome_result
        CHECK (
            result_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND CHAR_LENGTH(TRIM(event_key)) > 0
            AND JSON_TYPE(outcome_snapshot) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_leave_occupancy_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_key VARCHAR(191) NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    outcome_id BIGINT NOT NULL,
    generation_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    occupancy_date DATE NOT NULL,
    status ENUM('active', 'cancelled') NOT NULL DEFAULT 'active',
    active_marker TINYINT(1) NULL DEFAULT 1,
    cancelled_by VARCHAR(100) NULL,
    cancelled_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_leave_occupancy_outcome (outcome_id),
    UNIQUE KEY uq_scheduling_leave_occupancy_staff_date (
        staff_id,
        occupancy_date,
        active_marker
    ),
    INDEX idx_scheduling_leave_occupancy_generation (
        generation_id,
        active_marker
    ),
    CONSTRAINT fk_scheduling_leave_occupancy_outcome
        FOREIGN KEY (outcome_id, batch_key)
        REFERENCES scheduling_leave_substitution_outcomes(id, batch_key)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_occupancy_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_occupancy_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_occupancy_state
        CHECK (
            (
                status = 'active'
                AND active_marker = 1
                AND cancelled_by IS NULL
                AND cancelled_at IS NULL
            )
            OR (
                status = 'cancelled'
                AND active_marker IS NULL
                AND CHAR_LENGTH(TRIM(cancelled_by)) > 0
                AND cancelled_at IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_leave_substitution_receipts (
    batch_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
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
    outcome_event_ids JSON NOT NULL,
    result_snapshot JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_key),
    CONSTRAINT fk_scheduling_leave_receipt_batch
        FOREIGN KEY (batch_key)
        REFERENCES scheduling_leave_substitution_batches(batch_key)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_receipt_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_leave_receipt_scheduling
        FOREIGN KEY (scheduling_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_leave_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_scheduling_leave_receipt_versions
        CHECK (
            resulting_order_version = expected_order_version + 1
            AND resulting_scheduling_version =
                expected_scheduling_version + 1
            AND resulting_client_finance_version =
                expected_client_finance_version + 1
            AND resulting_payroll_version = expected_payroll_version + 1
        ),
    CONSTRAINT chk_scheduling_leave_receipt_snapshots
        CHECK (
            JSON_TYPE(outcome_event_ids) = 'ARRAY'
            AND JSON_TYPE(result_snapshot) = 'OBJECT'
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_scheduling_leave_batches_before_update;
CREATE TRIGGER trg_scheduling_leave_batches_before_update
BEFORE UPDATE ON scheduling_leave_substitution_batches
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_leave_batches_before_delete;
CREATE TRIGGER trg_scheduling_leave_batches_before_delete
BEFORE DELETE ON scheduling_leave_substitution_batches
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_leave_outcomes_before_update;
CREATE TRIGGER trg_scheduling_leave_outcomes_before_update
BEFORE UPDATE ON scheduling_leave_substitution_outcomes
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_leave_outcomes_before_delete;
CREATE TRIGGER trg_scheduling_leave_outcomes_before_delete
BEFORE DELETE ON scheduling_leave_substitution_outcomes
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_leave_receipts_before_update;
CREATE TRIGGER trg_scheduling_leave_receipts_before_update
BEFORE UPDATE ON scheduling_leave_substitution_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_leave_receipts_before_delete;
CREATE TRIGGER trg_scheduling_leave_receipts_before_delete
BEFORE DELETE ON scheduling_leave_substitution_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be deleted';

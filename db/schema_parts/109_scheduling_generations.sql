-- Additive Scheduling generation/effective metadata over the existing
-- case_staff_assignments and staff_schedule SSOT tables.

CREATE TABLE IF NOT EXISTS scheduling_aggregates (
    case_no VARCHAR(50) PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    generation_counter INT UNSIGNED NOT NULL DEFAULT 0,
    effective_generation_id BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_scheduling_aggregate_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_generations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    generation_number INT UNSIGNED NOT NULL,
    resulting_aggregate_version BIGINT UNSIGNED NOT NULL,
    status ENUM('preparing', 'effective', 'cancelled') NOT NULL,
    effective_marker TINYINT(1) NULL,
    created_by VARCHAR(100) NOT NULL,
    change_reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelled_at TIMESTAMP NULL,
    UNIQUE KEY uq_scheduling_generation_identity (id, case_no),
    UNIQUE KEY uq_scheduling_generation_number (case_no, generation_number),
    UNIQUE KEY uq_scheduling_generation_version (
        case_no,
        resulting_aggregate_version
    ),
    UNIQUE KEY uq_scheduling_generation_effective (case_no, effective_marker),
    CONSTRAINT fk_scheduling_generation_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_generation_number
        CHECK (generation_number > 0),
    CONSTRAINT chk_scheduling_generation_version
        CHECK (resulting_aggregate_version > 0),
    CONSTRAINT chk_scheduling_generation_state
        CHECK (
            (
                status = 'effective'
                AND effective_marker = 1
                AND cancelled_at IS NULL
            )
            OR (
                status = 'preparing'
                AND effective_marker IS NULL
                AND cancelled_at IS NULL
            )
            OR (
                status = 'cancelled'
                AND effective_marker IS NULL
                AND cancelled_at IS NOT NULL
            )
        ),
    CONSTRAINT chk_scheduling_generation_actor
        CHECK (CHAR_LENGTH(TRIM(created_by)) > 0),
    CONSTRAINT chk_scheduling_generation_reason
        CHECK (CHAR_LENGTH(TRIM(change_reason)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE scheduling_aggregates
    ADD CONSTRAINT fk_scheduling_aggregate_effective_generation
        FOREIGN KEY (effective_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE case_staff_assignments
    DROP INDEX uq_case_assignment_sequence,
    ADD COLUMN generation_id BIGINT NULL AFTER case_no,
    ADD COLUMN candidate_key VARCHAR(191) NULL AFTER generation_id,
    ADD UNIQUE KEY uq_case_assignment_candidate (candidate_key),
    ADD UNIQUE KEY uq_case_assignment_generation_sequence (
        generation_id,
        assignment_sequence
    ),
    ADD UNIQUE KEY uq_case_assignment_generation (
        id,
        generation_id
    ),
    ADD UNIQUE KEY uq_case_assignment_generation_staff (
        id,
        generation_id,
        staff_id
    ),
    ADD UNIQUE KEY uq_case_assignment_case_staff (
        id,
        case_no,
        staff_id
    ),
    ADD INDEX idx_case_assignment_case_no (case_no),
    ADD CONSTRAINT fk_case_assignment_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE staff_schedule
    DROP INDEX ukey_staff_date,
    ADD COLUMN generation_id BIGINT NULL AFTER assignment_id,
    ADD COLUMN effective_marker TINYINT(1) NULL DEFAULT 1 AFTER is_double_pay,
    ADD UNIQUE KEY uq_staff_schedule_effective_date (
        staff_id,
        work_date,
        effective_marker
    ),
    ADD UNIQUE KEY uq_staff_schedule_generation_owner (
        generation_id,
        work_date
    ),
    ADD CONSTRAINT fk_staff_schedule_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS scheduling_buffer_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    generation_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    buffer_date DATE NOT NULL,
    status ENUM('active', 'released', 'cancelled') NOT NULL DEFAULT 'active',
    active_marker TINYINT(1) NULL DEFAULT 1,
    released_by VARCHAR(100) NULL,
    released_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_buffer_assignment_date (
        assignment_id,
        buffer_date
    ),
    UNIQUE KEY uq_scheduling_buffer_staff_date_active (
        staff_id,
        buffer_date,
        active_marker
    ),
    CONSTRAINT fk_scheduling_buffer_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_buffer_assignment
        FOREIGN KEY (assignment_id, generation_id, staff_id)
        REFERENCES case_staff_assignments(id, generation_id, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_buffer_state
        CHECK (
            (
                status = 'active'
                AND active_marker = 1
                AND released_by IS NULL
                AND released_at IS NULL
            )
            OR (
                status IN ('released', 'cancelled')
                AND active_marker IS NULL
                AND CHAR_LENGTH(TRIM(released_by)) > 0
                AND released_at IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_effective_occupancy (
    staff_id INT NOT NULL,
    occupancy_date DATE NOT NULL,
    generation_id BIGINT NOT NULL,
    assignment_id BIGINT NOT NULL,
    occupancy_type ENUM('assignment_interval', 'buffer') NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (staff_id, occupancy_date),
    INDEX idx_scheduling_effective_occupancy_generation (generation_id),
    CONSTRAINT fk_scheduling_occupancy_generation
        FOREIGN KEY (generation_id) REFERENCES scheduling_generations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_occupancy_assignment
        FOREIGN KEY (assignment_id, generation_id, staff_id)
        REFERENCES case_staff_assignments(id, generation_id, staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_rebuild_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    previous_generation_id BIGINT NULL,
    new_generation_id BIGINT NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_rebuild_idempotency (idempotency_key),
    UNIQUE KEY uq_scheduling_rebuild_generation (
        id,
        new_generation_id
    ),
    CONSTRAINT fk_scheduling_rebuild_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_rebuild_previous_generation
        FOREIGN KEY (previous_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_rebuild_new_generation
        FOREIGN KEY (new_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_rebuild_version
        CHECK (
            resulting_scheduling_version = expected_scheduling_version + 1
        ),
    CONSTRAINT chk_scheduling_rebuild_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_rebuild_lineage (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rebuild_event_id BIGINT NOT NULL,
    old_assignment_identity VARCHAR(191) NOT NULL,
    new_assignment_id BIGINT NOT NULL,
    new_generation_id BIGINT NOT NULL,
    lineage_ordinal INT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_rebuild_lineage (
        rebuild_event_id,
        old_assignment_identity,
        new_assignment_id
    ),
    UNIQUE KEY uq_scheduling_rebuild_lineage_ordinal (
        rebuild_event_id,
        lineage_ordinal
    ),
    CONSTRAINT fk_scheduling_rebuild_lineage_event
        FOREIGN KEY (rebuild_event_id, new_generation_id)
        REFERENCES scheduling_rebuild_events(id, new_generation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_rebuild_lineage_assignment
        FOREIGN KEY (new_assignment_id, new_generation_id)
        REFERENCES case_staff_assignments(id, generation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_command_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_family VARCHAR(100) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    expected_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_scheduling_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_id BIGINT NOT NULL,
    rebuild_event_id BIGINT NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_command_receipt_key (idempotency_key),
    CONSTRAINT fk_scheduling_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_receipt_generation
        FOREIGN KEY (resulting_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_receipt_rebuild
        FOREIGN KEY (rebuild_event_id) REFERENCES scheduling_rebuild_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_receipt_version
        CHECK (
            resulting_scheduling_version = expected_scheduling_version + 1
        ),
    CONSTRAINT chk_scheduling_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_scheduling_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_bootstrap_review_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    issue_code VARCHAR(32) NOT NULL,
    migration_identity VARCHAR(100) NOT NULL,
    evidence_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_scheduling_bootstrap_review_issue (
        case_no,
        issue_code,
        migration_identity
    ),
    CONSTRAINT fk_scheduling_bootstrap_review_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_bootstrap_review_code
        CHECK (issue_code REGEXP '^SCHED-BOOT-[0-9]{3}$'),
    CONSTRAINT chk_scheduling_bootstrap_review_migration
        CHECK (CHAR_LENGTH(TRIM(migration_identity)) > 0),
    CONSTRAINT chk_scheduling_bootstrap_review_evidence
        CHECK (JSON_TYPE(evidence_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_events_before_update;
CREATE TRIGGER trg_scheduling_rebuild_events_before_update
BEFORE UPDATE ON scheduling_rebuild_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_events_before_delete;
CREATE TRIGGER trg_scheduling_rebuild_events_before_delete
BEFORE DELETE ON scheduling_rebuild_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_lineage_before_update;
CREATE TRIGGER trg_scheduling_rebuild_lineage_before_update
BEFORE UPDATE ON scheduling_rebuild_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_rebuild_lineage_before_delete;
CREATE TRIGGER trg_scheduling_rebuild_lineage_before_delete
BEFORE DELETE ON scheduling_rebuild_lineage
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_command_receipts_before_update;
CREATE TRIGGER trg_scheduling_command_receipts_before_update
BEFORE UPDATE ON scheduling_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_command_receipts_before_delete;
CREATE TRIGGER trg_scheduling_command_receipts_before_delete
BEFORE DELETE ON scheduling_command_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_scheduling_bootstrap_review_events_before_update;
CREATE TRIGGER trg_scheduling_bootstrap_review_events_before_update
BEFORE UPDATE ON scheduling_bootstrap_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_scheduling_bootstrap_review_events_before_delete;
CREATE TRIGGER trg_scheduling_bootstrap_review_events_before_delete
BEFORE DELETE ON scheduling_bootstrap_review_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be deleted';

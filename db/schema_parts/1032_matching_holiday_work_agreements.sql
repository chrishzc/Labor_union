-- File: 1032_matching_holiday_work_agreements.sql
-- Description: Scheduling-owned immutable records for a current matching plan's national-holiday work agreement.
-- Data effect: schema_only; no existing matching decision, calendar, or assignment row is rewritten.

CREATE TABLE IF NOT EXISTS matching_holiday_work_agreements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    holiday_date DATE NOT NULL,
    plan_version INT UNSIGNED NOT NULL,
    agreement_status ENUM('accepted', 'declined') NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_matching_holiday_work_agreement_idempotency (idempotency_key),
    INDEX idx_matching_holiday_work_agreement_current (plan_id, holiday_date, plan_version, id),
    CONSTRAINT fk_matching_holiday_work_agreement_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_holiday_work_agreement_fingerprint CHECK (
        preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_holiday_work_agreement_reason CHECK (
        CHAR_LENGTH(TRIM(reason)) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_holiday_work_agreement_participants (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    agreement_id BIGINT UNSIGNED NOT NULL,
    participant_role ENUM('customer', 'caregiver') NOT NULL,
    segment_id BIGINT NULL,
    participant_key VARCHAR(64) NOT NULL,
    decision ENUM('accepted', 'declined') NOT NULL,
    created_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_matching_holiday_work_agreement_participant (agreement_id, participant_key),
    INDEX idx_matching_holiday_work_agreement_participant_segment (segment_id, agreement_id),
    CONSTRAINT fk_matching_holiday_work_agreement_participant_agreement FOREIGN KEY (agreement_id)
        REFERENCES matching_holiday_work_agreements(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_holiday_work_agreement_participant_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_holiday_work_agreement_participant_target CHECK (
        (participant_role = 'customer' AND segment_id IS NULL AND participant_key = 'customer')
        OR
        (participant_role = 'caregiver' AND segment_id IS NOT NULL
         AND participant_key = (
             CONCAT('segment:', CAST(segment_id AS CHAR))
             COLLATE utf8mb4_unicode_ci
         ))
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_matching_holiday_work_agreements_before_update;
CREATE TRIGGER trg_matching_holiday_work_agreements_before_update
BEFORE UPDATE ON matching_holiday_work_agreements
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching holiday work agreements cannot be updated';

DROP TRIGGER IF EXISTS trg_matching_holiday_work_agreements_before_delete;
CREATE TRIGGER trg_matching_holiday_work_agreements_before_delete
BEFORE DELETE ON matching_holiday_work_agreements
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching holiday work agreements cannot be deleted';

DROP TRIGGER IF EXISTS trg_matching_holiday_work_agreement_participants_before_update;
CREATE TRIGGER trg_matching_holiday_work_agreement_participants_before_update
BEFORE UPDATE ON matching_holiday_work_agreement_participants
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching holiday work agreement participants cannot be updated';

DROP TRIGGER IF EXISTS trg_matching_holiday_work_agreement_participants_before_delete;
CREATE TRIGGER trg_matching_holiday_work_agreement_participants_before_delete
BEFORE DELETE ON matching_holiday_work_agreement_participants
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching holiday work agreement participants cannot be deleted';

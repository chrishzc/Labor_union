-- WP68 confirmed service dates, schedule snapshots and confirmation events.

CREATE TABLE IF NOT EXISTS confirmed_service_date_versions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    version INT UNSIGNED NOT NULL,
    order_version INT UNSIGNED NOT NULL,
    scheduling_version INT UNSIGNED NOT NULL,
    service_day_count INT UNSIGNED NOT NULL,
    service_date_fingerprint CHAR(64) NOT NULL,
    is_current TINYINT NULL,
    confirmed_by_actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NULL,
    confirmed_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    invalidated_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_confirmed_service_date_version (case_no,version),
    UNIQUE KEY uq_confirmed_service_date_current (case_no,is_current),
    CONSTRAINT fk_confirmed_service_date_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT chk_confirmed_service_date_fingerprint CHECK (service_date_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_confirmed_service_date_current CHECK (is_current IS NULL OR is_current=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS confirmed_service_date_days (
    confirmed_version_id BIGINT UNSIGNED NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    service_date DATE NOT NULL,
    PRIMARY KEY (confirmed_version_id,ordinal),
    UNIQUE KEY uq_confirmed_service_date_day (confirmed_version_id,service_date),
    CONSTRAINT fk_confirmed_service_date_day_version FOREIGN KEY (confirmed_version_id)
        REFERENCES confirmed_service_date_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS confirmed_service_date_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    confirmed_version_id BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_confirmed_service_date_receipt_key (idempotency_key),
    CONSTRAINT fk_confirmed_service_date_receipt_version FOREIGN KEY (confirmed_version_id)
        REFERENCES confirmed_service_date_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    plan_id BIGINT NOT NULL,
    confirmed_version_id BIGINT UNSIGNED NOT NULL,
    snapshot_fingerprint CHAR(64) NOT NULL,
    status ENUM('draft','sent','invalidated') NOT NULL DEFAULT 'draft',
    current_marker TINYINT NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    invalidated_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_matching_schedule_current (case_no,current_marker),
    CONSTRAINT fk_matching_schedule_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_matching_schedule_plan FOREIGN KEY (plan_id) REFERENCES caregiver_matching_plans(id),
    CONSTRAINT fk_matching_schedule_version FOREIGN KEY (confirmed_version_id)
        REFERENCES confirmed_service_date_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_recipient_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    parent_snapshot_id BIGINT UNSIGNED NOT NULL,
    audience_type ENUM('customer','caregiver') NOT NULL,
    recipient_key VARCHAR(191) NOT NULL,
    segment_id BIGINT NULL,
    recipient_line_user_id VARCHAR(191) NULL,
    payload_snapshot JSON NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    delivery_status ENUM('pending','queued','sent','failed','blocked') NOT NULL DEFAULT 'pending',
    UNIQUE KEY uq_matching_schedule_recipient (parent_snapshot_id,recipient_key),
    CONSTRAINT fk_matching_schedule_recipient_parent FOREIGN KEY (parent_snapshot_id)
        REFERENCES matching_schedule_snapshots(id),
    CONSTRAINT fk_matching_schedule_recipient_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id),
    CONSTRAINT chk_matching_schedule_recipient_target CHECK (
        (audience_type='customer' AND segment_id IS NULL) OR
        (audience_type='caregiver' AND segment_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_confirmation_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recipient_snapshot_id BIGINT UNSIGNED NOT NULL,
    confirmation_value ENUM('confirmed','rejected','manually_confirmed','manually_revoked') NOT NULL,
    source ENUM('line','admin') NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_schedule_confirmation_key (idempotency_key),
    CONSTRAINT fk_matching_schedule_confirmation_recipient FOREIGN KEY (recipient_snapshot_id)
        REFERENCES matching_schedule_recipient_snapshots(id),
    CONSTRAINT chk_matching_schedule_rejection_reason CHECK (
        confirmation_value<>'rejected' OR CHAR_LENGTH(TRIM(reason))>0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_schedule_line_interactions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recipient_snapshot_id BIGINT UNSIGNED NOT NULL,
    token_hash CHAR(64) NOT NULL,
    interaction_status ENUM('active','awaiting_rejection_reason','consumed','invalidated') NOT NULL DEFAULT 'active',
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    consumed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_matching_schedule_line_token (token_hash),
    UNIQUE KEY uq_matching_schedule_recipient_interaction (recipient_snapshot_id),
    CONSTRAINT fk_matching_schedule_interaction_recipient FOREIGN KEY (recipient_snapshot_id)
        REFERENCES matching_schedule_recipient_snapshots(id),
    CONSTRAINT chk_matching_schedule_line_token CHECK (token_hash REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

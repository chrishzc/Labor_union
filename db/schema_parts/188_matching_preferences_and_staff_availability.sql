-- WP72 additive Staff Matching Profile and Scheduling availability roots.

ALTER TABLE orders
    ADD COLUMN requires_cooking TINYINT(1) NULL
        COMMENT '是否需要月嫂下廚；NULL 只允許 legacy/待人工補正',
    ADD CONSTRAINT chk_orders_requires_cooking
        CHECK (requires_cooking IS NULL OR requires_cooking IN (0, 1));

CREATE TABLE IF NOT EXISTS staff_matching_preference_definitions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    preference_key VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    value_kind ENUM('integer_range','integer_set') NOT NULL,
    is_filterable TINYINT(1) NOT NULL DEFAULT 0,
    order_fact_key ENUM('service_days','service_hours_per_day') NULL,
    comparison_operator ENUM('range_with_tolerance','contains_integer') NOT NULL,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    created_by VARCHAR(100) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_matching_preference_key (preference_key),
    CONSTRAINT chk_staff_matching_preference_definition_text CHECK (
        CHAR_LENGTH(TRIM(preference_key)) > 0
        AND CHAR_LENGTH(TRIM(display_name)) > 0
        AND CHAR_LENGTH(TRIM(created_by)) > 0
        AND CHAR_LENGTH(TRIM(updated_by)) > 0
    ),
    CONSTRAINT chk_staff_matching_preference_filter_source CHECK (
        (is_filterable=0 AND order_fact_key IS NULL)
        OR (is_filterable=1 AND order_fact_key IS NOT NULL)
    ),
    CONSTRAINT chk_staff_matching_preference_comparison CHECK (
        (value_kind='integer_range' AND comparison_operator='range_with_tolerance')
        OR (value_kind='integer_set' AND comparison_operator='contains_integer')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_profiles (
    staff_id INT PRIMARY KEY,
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_by VARCHAR(100) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_matching_preference_profile_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_matching_preference_profile_actor
        CHECK (CHAR_LENGTH(TRIM(updated_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_values (
    staff_id INT NOT NULL,
    definition_id BIGINT NOT NULL,
    value_json JSON NOT NULL,
    profile_version BIGINT UNSIGNED NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (staff_id,definition_id),
    CONSTRAINT fk_staff_matching_preference_value_profile
        FOREIGN KEY (staff_id) REFERENCES staff_matching_preference_profiles(staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_matching_preference_value_definition
        FOREIGN KEY (definition_id) REFERENCES staff_matching_preference_definitions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_matching_preference_value_json
        CHECK (JSON_TYPE(value_json)='OBJECT'),
    CONSTRAINT chk_staff_matching_preference_value_actor
        CHECK (CHAR_LENGTH(TRIM(updated_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    before_json JSON NOT NULL,
    after_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_matching_preference_event_key (idempotency_key),
    CONSTRAINT chk_staff_matching_preference_event_snapshots CHECK (
        resulting_version>0
        AND JSON_TYPE(before_json)='OBJECT'
        AND JSON_TYPE(after_json)='OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT chk_staff_matching_preference_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_staff_matching_preference_receipt_snapshot
        CHECK (JSON_TYPE(result_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_matching_preference_migration_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    source_kind ENUM('staff_time_slot') NOT NULL,
    source_value VARCHAR(100) NOT NULL,
    issue_code ENUM('source_not_ready') NOT NULL,
    status ENUM('open','resolved') NOT NULL DEFAULT 'open',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    resolved_at DATETIME(6) NULL,
    UNIQUE KEY uq_staff_matching_preference_migration_review
        (staff_id,source_kind,source_value,issue_code),
    CONSTRAINT fk_staff_matching_preference_migration_review_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_availability_aggregates (
    staff_id INT PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_scheduling_staff_availability_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_unavailability_blocks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    block_kind ENUM('long_leave','paused_service') NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    status ENUM('effective','cancelled') NOT NULL DEFAULT 'effective',
    reason VARCHAR(500) NOT NULL,
    source_block_id BIGINT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ended_by VARCHAR(100) NULL,
    ended_at DATETIME(6) NULL,
    cancelled_by VARCHAR(100) NULL,
    cancelled_at DATETIME(6) NULL,
    CONSTRAINT fk_scheduling_staff_unavailability_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_staff_unavailability_source
        FOREIGN KEY (source_block_id) REFERENCES scheduling_staff_unavailability_blocks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_staff_unavailability_dates CHECK (
        (block_kind='long_leave' AND end_date IS NOT NULL AND end_date>=start_date)
        OR (block_kind='paused_service' AND (end_date IS NULL OR end_date>=start_date))
    ),
    CONSTRAINT chk_scheduling_staff_unavailability_reason
        CHECK (CHAR_LENGTH(TRIM(reason))>0 AND CHAR_LENGTH(TRIM(created_by))>0),
    INDEX idx_scheduling_staff_unavailability_current
        (staff_id,status,start_date,end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_availability_events (
    event_key VARCHAR(191) PRIMARY KEY,
    staff_id INT NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    block_id BIGINT NOT NULL,
    event_type ENUM('created','pause_ended','cancelled') NOT NULL,
    before_snapshot JSON NOT NULL,
    after_snapshot JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_scheduling_staff_availability_event_staff
        FOREIGN KEY (staff_id) REFERENCES scheduling_staff_availability_aggregates(staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_staff_availability_event_block
        FOREIGN KEY (block_id) REFERENCES scheduling_staff_unavailability_blocks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_staff_availability_event_snapshots CHECK (
        aggregate_version>0
        AND JSON_TYPE(before_snapshot)='OBJECT'
        AND JSON_TYPE(after_snapshot)='OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_staff_availability_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    request_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    block_id BIGINT NOT NULL,
    action ENUM('create_long_leave','create_pause','end_pause','cancel') NOT NULL,
    result_snapshot JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_scheduling_staff_availability_receipt_staff
        FOREIGN KEY (staff_id) REFERENCES scheduling_staff_availability_aggregates(staff_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_scheduling_staff_availability_receipt_block
        FOREIGN KEY (block_id) REFERENCES scheduling_staff_unavailability_blocks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_scheduling_staff_availability_receipt_fingerprints CHECK (
        request_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_scheduling_staff_availability_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO staff_matching_preference_definitions
    (preference_key,display_name,value_kind,is_filterable,order_fact_key,
     comparison_operator,status,version,created_by,updated_by)
VALUES
    ('preferred_service_days','可承接服務天數','integer_range',1,
     'service_days','range_with_tolerance','active',1,'wp72','wp72'),
    ('daily_service_hours','可承接每日服務時數','integer_set',1,
     'service_hours_per_day','contains_integer','active',1,'wp72','wp72')
ON DUPLICATE KEY UPDATE preference_key=VALUES(preference_key);

INSERT INTO staff_matching_preference_profiles
    (staff_id,version,created_by,updated_by)
SELECT DISTINCT staff_id,1,'wp72-time-slot-backfill','wp72-time-slot-backfill'
FROM staff_time_slots
WHERE slot_name IN (
    '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
    '4小時(下午13:00-17:00)','8小時','24小時'
)
ON DUPLICATE KEY UPDATE staff_id=VALUES(staff_id);

INSERT INTO staff_matching_preference_values
    (staff_id,definition_id,value_json,profile_version,updated_by)
SELECT normalized.staff_id,definition.id,
       JSON_OBJECT(
           'values',
           CAST(CONCAT('[',GROUP_CONCAT(
               normalized.hours ORDER BY normalized.hours SEPARATOR ','
           ),']') AS JSON)
       ),1,
       'wp72-time-slot-backfill'
FROM (
    SELECT DISTINCT staff_id,
        CASE
            WHEN slot_name IN (
                '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
                '4小時(下午13:00-17:00)'
            ) THEN 4
            WHEN slot_name='8小時' THEN 8
            WHEN slot_name='24小時' THEN 24
        END AS hours
    FROM staff_time_slots
    WHERE slot_name IN (
        '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
        '4小時(下午13:00-17:00)','8小時','24小時'
    )
) normalized
JOIN staff_matching_preference_definitions definition
  ON definition.preference_key='daily_service_hours'
GROUP BY normalized.staff_id,definition.id
ON DUPLICATE KEY UPDATE staff_id=VALUES(staff_id);

INSERT INTO staff_matching_preference_migration_reviews
    (staff_id,source_kind,source_value,issue_code)
SELECT staff_id,'staff_time_slot',
       LEFT(CASE
           WHEN custom_slot_detail IS NULL OR TRIM(custom_slot_detail)='' THEN slot_name
           ELSE CONCAT(slot_name,':',custom_slot_detail)
       END,100),
       'source_not_ready'
FROM staff_time_slots
WHERE slot_name NOT IN (
    '4小時_上午','4小時_下午','4小時(上午8:30-12:30)',
    '4小時(下午13:00-17:00)','8小時','24小時'
)
   OR (custom_slot_detail IS NOT NULL AND TRIM(custom_slot_detail)<>'')
ON DUPLICATE KEY UPDATE id=id;

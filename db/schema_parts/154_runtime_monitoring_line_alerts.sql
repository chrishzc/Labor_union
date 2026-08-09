-- Runtime monitoring projections and canonical LINE alert notification targets.

CREATE TABLE IF NOT EXISTS runtime_service_heartbeats (
    service_name VARCHAR(100) NOT NULL,
    instance_id VARCHAR(191) NOT NULL,
    process_id BIGINT NULL,
    host_name VARCHAR(191) NOT NULL,
    service_status ENUM('starting','running','degraded','stopped') NOT NULL,
    details_snapshot JSON NOT NULL,
    started_at_utc DATETIME(6) NOT NULL,
    last_seen_at_utc DATETIME(6) NOT NULL,
    stopped_at_utc DATETIME(6) NULL,
    PRIMARY KEY (service_name, instance_id),
    INDEX idx_runtime_service_latest (service_name, last_seen_at_utc),
    CONSTRAINT chk_runtime_service_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS runtime_health_status (
    check_name VARCHAR(100) PRIMARY KEY,
    component VARCHAR(100) NOT NULL,
    health_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NOT NULL,
    raw_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    details_snapshot JSON NOT NULL,
    response_ms INT UNSIGNED NULL,
    consecutive_failures INT UNSIGNED NOT NULL DEFAULT 0,
    consecutive_successes INT UNSIGNED NOT NULL DEFAULT 0,
    checked_at_utc DATETIME(6) NOT NULL,
    last_success_at_utc DATETIME(6) NULL,
    status_changed_at_utc DATETIME(6) NOT NULL,
    CONSTRAINT chk_runtime_health_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS runtime_health_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    check_name VARCHAR(100) NOT NULL,
    component VARCHAR(100) NOT NULL,
    transition_type ENUM(
        'opened','escalated','reminder','recovered','test'
    ) NOT NULL,
    before_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NULL,
    resulting_status ENUM(
        'healthy','warning','critical','unknown','maintenance'
    ) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    details_snapshot JSON NOT NULL,
    event_fingerprint CHAR(64) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_runtime_health_event_fingerprint (event_fingerprint),
    INDEX idx_runtime_health_event_check (check_name, occurred_at_utc, id),
    CONSTRAINT chk_runtime_health_event_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT'),
    CONSTRAINT chk_runtime_health_event_fingerprint
        CHECK (event_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_alert_notification_targets (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    target_type ENUM('admin_user','group') NOT NULL,
    admin_user_id BIGINT NULL,
    group_id VARCHAR(191) NULL,
    display_name VARCHAR(191) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    minimum_status ENUM('warning','critical') NOT NULL DEFAULT 'warning',
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_alert_admin_target (admin_user_id),
    UNIQUE KEY uq_line_alert_group_target (group_id),
    CONSTRAINT fk_line_alert_admin_target
        FOREIGN KEY (admin_user_id) REFERENCES admin_users(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_alert_target_identity CHECK (
        (target_type='admin_user' AND admin_user_id IS NOT NULL AND group_id IS NULL)
        OR
        (target_type='group' AND admin_user_id IS NULL AND group_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_alert_delivery_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    health_event_id BIGINT UNSIGNED NOT NULL,
    target_id BIGINT UNSIGNED NOT NULL,
    delivery_task_id BIGINT UNSIGNED NULL,
    projection_status ENUM('queued','skipped','failed') NOT NULL,
    resolved_line_target_type ENUM('user','group') NULL,
    resolved_line_target_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_alert_delivery_intent (health_event_id, target_id),
    INDEX idx_line_alert_delivery_task (delivery_task_id),
    CONSTRAINT fk_line_alert_intent_event
        FOREIGN KEY (health_event_id) REFERENCES runtime_health_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_alert_intent_target
        FOREIGN KEY (target_id) REFERENCES line_alert_notification_targets(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_line_alert_intent_delivery
        FOREIGN KEY (delivery_task_id) REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_runtime_health_events_before_update;
CREATE TRIGGER trg_runtime_health_events_before_update
BEFORE UPDATE ON runtime_health_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'runtime_health_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_runtime_health_events_before_delete;
CREATE TRIGGER trg_runtime_health_events_before_delete
BEFORE DELETE ON runtime_health_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'runtime_health_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_alert_delivery_intents_before_update;
CREATE TRIGGER trg_line_alert_delivery_intents_before_update
BEFORE UPDATE ON line_alert_delivery_intents
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_alert_delivery_intents records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_alert_delivery_intents_before_delete;
CREATE TRIGGER trg_line_alert_delivery_intents_before_delete
BEFORE DELETE ON line_alert_delivery_intents
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_alert_delivery_intents records cannot be deleted';

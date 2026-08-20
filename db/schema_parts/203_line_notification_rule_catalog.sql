-- File: 203_line_notification_rule_catalog.sql
-- Description: 新增 LINE 可配置通知規則的來源事件、決策與意圖稽核資料模型。

ALTER TABLE line_configuration_revisions
    MODIFY COLUMN configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules'
    ) NOT NULL;

ALTER TABLE line_configuration_current
    MODIFY COLUMN configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS line_notification_source_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_domain VARCHAR(64) NOT NULL,
    event_code VARCHAR(64) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_aggregate_type VARCHAR(191) NOT NULL,
    source_aggregate_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    historical_silent BOOLEAN NOT NULL DEFAULT FALSE,
    facts_snapshot JSON NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_notification_source_identity (source_domain,event_code,source_event_identity),
    INDEX idx_line_notification_source_due (event_code,historical_silent,occurred_at_utc,id),
    CONSTRAINT chk_line_notification_source_facts CHECK (JSON_TYPE(facts_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_notification_decisions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_event_id BIGINT UNSIGNED NOT NULL,
    rule_revision_id BIGINT UNSIGNED NOT NULL,
    rule_id VARCHAR(64) NOT NULL,
    recipient_selector VARCHAR(64) NOT NULL,
    recipient_type ENUM('user','group','room') NULL,
    recipient_identity VARCHAR(191) NOT NULL DEFAULT '',
    decision_status ENUM('suppressed','intent_created','cancelled_stale') NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    decision_snapshot JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_notification_decision (source_event_id,rule_revision_id,rule_id,recipient_selector,recipient_identity),
    INDEX idx_line_notification_decision_source (source_event_id,id),
    CONSTRAINT fk_line_notification_decision_source FOREIGN KEY (source_event_id) REFERENCES line_notification_source_events(id),
    CONSTRAINT fk_line_notification_decision_revision FOREIGN KEY (rule_revision_id) REFERENCES line_configuration_revisions(id),
    CONSTRAINT chk_line_notification_decision_snapshot CHECK (JSON_TYPE(decision_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_notification_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    decision_id BIGINT UNSIGNED NOT NULL,
    delivery_task_id BIGINT UNSIGNED NULL,
    template_revision_id BIGINT UNSIGNED NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    payload_snapshot JSON NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    scheduled_at_utc DATETIME(6) NOT NULL,
    intent_status ENUM('scheduled','cancelled','provider_accepted') NOT NULL DEFAULT 'scheduled',
    cancellation_reason VARCHAR(64) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    cancelled_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_line_notification_intent_decision (decision_id),
    UNIQUE KEY uq_line_notification_intent_delivery (delivery_task_id),
    INDEX idx_line_notification_intent_status (intent_status,scheduled_at_utc,id),
    CONSTRAINT fk_line_notification_intent_decision FOREIGN KEY (decision_id) REFERENCES line_notification_decisions(id),
    CONSTRAINT fk_line_notification_intent_delivery FOREIGN KEY (delivery_task_id) REFERENCES line_delivery_tasks(id),
    CONSTRAINT fk_line_notification_intent_template FOREIGN KEY (template_revision_id) REFERENCES line_configuration_revisions(id),
    CONSTRAINT chk_line_notification_intent_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT'),
    CONSTRAINT chk_line_notification_intent_fingerprint CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER trg_line_notification_source_events_before_update
BEFORE UPDATE ON line_notification_source_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_source_events records cannot be updated';

CREATE TRIGGER trg_line_notification_source_events_before_delete
BEFORE DELETE ON line_notification_source_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_source_events records cannot be deleted';

CREATE TRIGGER trg_line_notification_decisions_before_update
BEFORE UPDATE ON line_notification_decisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_decisions records cannot be updated';

CREATE TRIGGER trg_line_notification_decisions_before_delete
BEFORE DELETE ON line_notification_decisions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_decisions records cannot be deleted';

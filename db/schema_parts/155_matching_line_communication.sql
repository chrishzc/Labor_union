-- Canonical matching notification intents, one-time LINE actions, and responses.

SET @matching_communication_version_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'caregiver_matching_plans'
      AND COLUMN_NAME = 'communication_version'
);
SET @matching_communication_version_sql = IF(
    @matching_communication_version_exists = 0,
    'ALTER TABLE `caregiver_matching_plans` ADD COLUMN `communication_version` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT ''配對通知與回覆的 optimistic version'' AFTER `version`',
    'SELECT 1'
);
PREPARE matching_communication_version_stmt FROM @matching_communication_version_sql;
EXECUTE matching_communication_version_stmt;
DEALLOCATE PREPARE matching_communication_version_stmt;

CREATE TABLE IF NOT EXISTS matching_notification_intents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    notification_kind ENUM(
        'caregiver_info_1','caregiver_info_2','customer_profiles'
    ) NOT NULL,
    recipient_line_user_id VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    projection_status ENUM('pending','projected','failed','cancelled')
        NOT NULL DEFAULT 'pending',
    delivery_task_id BIGINT UNSIGNED NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    projected_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_matching_notification_idempotency (idempotency_key),
    INDEX idx_matching_notification_plan (plan_id, created_at_utc, id),
    INDEX idx_matching_notification_segment (segment_id, created_at_utc, id),
    INDEX idx_matching_notification_delivery (delivery_task_id),
    CONSTRAINT fk_matching_notification_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_notification_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_notification_delivery FOREIGN KEY (delivery_task_id)
        REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_notification_payload CHECK (
        JSON_TYPE(payload_snapshot) = 'OBJECT'
    ),
    CONSTRAINT chk_matching_notification_fingerprint CHECK (
        payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_notification_target CHECK (
        (notification_kind IN ('caregiver_info_1','caregiver_info_2') AND segment_id IS NOT NULL)
        OR (notification_kind='customer_profiles' AND segment_id IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_line_interactions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    token_hash CHAR(64) NOT NULL,
    plan_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    action_scope ENUM('caregiver_willingness','customer_decision') NOT NULL,
    recipient_line_user_id VARCHAR(191) NOT NULL,
    interaction_status ENUM('active','consumed','expired','revoked')
        NOT NULL DEFAULT 'active',
    expires_at_utc DATETIME(6) NOT NULL,
    consumed_at_utc DATETIME(6) NULL,
    consumed_by_line_user_id VARCHAR(191) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_matching_line_interaction_token (token_hash),
    INDEX idx_matching_line_interaction_plan (plan_id, action_scope, interaction_status),
    CONSTRAINT fk_matching_line_interaction_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_line_interaction_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_line_interaction_token CHECK (
        token_hash REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_line_interaction_target CHECK (
        (action_scope='caregiver_willingness' AND segment_id IS NOT NULL)
        OR (action_scope='customer_decision' AND segment_id IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS matching_response_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    response_type ENUM('caregiver_willingness','customer_decision') NOT NULL,
    response_value ENUM(
        'willing','unwilling','accepted','declined','contact_requested'
    ) NOT NULL,
    response_source ENUM('line','admin') NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    line_user_id VARCHAR(191) NULL,
    reason VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    UNIQUE KEY uq_matching_response_idempotency (idempotency_key),
    INDEX idx_matching_response_plan (plan_id, occurred_at_utc, id),
    INDEX idx_matching_response_segment (segment_id, occurred_at_utc, id),
    CONSTRAINT fk_matching_response_plan FOREIGN KEY (plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_matching_response_segment FOREIGN KEY (segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_matching_response_fingerprint CHECK (
        payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_matching_response_target CHECK (
        (response_type='caregiver_willingness'
         AND segment_id IS NOT NULL
         AND response_value IN ('willing','unwilling'))
        OR
        (response_type='customer_decision'
         AND segment_id IS NULL
         AND response_value IN ('accepted','declined','contact_requested'))
    ),
    CONSTRAINT chk_matching_response_manual_reason CHECK (
        response_source='line' OR CHAR_LENGTH(TRIM(reason)) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO matching_response_events (
    plan_id, segment_id, response_type, response_value, response_source,
    actor_id, line_user_id, reason, idempotency_key, payload_fingerprint,
    occurred_at_utc
)
SELECT legacy.plan_id,
       legacy.segment_id,
       'caregiver_willingness',
       JSON_UNQUOTE(JSON_EXTRACT(legacy.payload, '$.willingness')),
       'admin',
       legacy.actor,
       NULL,
       'Stage 7 migrated legacy willingness event',
       CONCAT('legacy-matching-response:', legacy.id),
       SHA2(CONCAT_WS('|', legacy.plan_id, legacy.segment_id,
           JSON_UNQUOTE(JSON_EXTRACT(legacy.payload, '$.willingness')),
           legacy.event_key), 256),
       legacy.occurred_at
FROM caregiver_matching_plan_events legacy
WHERE legacy.event_type = 'willingness_changed'
  AND JSON_UNQUOTE(JSON_EXTRACT(legacy.payload, '$.willingness'))
      IN ('willing','unwilling')
  AND NOT EXISTS (
      SELECT 1
      FROM caregiver_matching_plan_events newer
      WHERE newer.plan_id = legacy.plan_id
        AND newer.segment_id = legacy.segment_id
        AND newer.event_type = 'willingness_changed'
        AND (
            newer.occurred_at > legacy.occurred_at
            OR (newer.occurred_at = legacy.occurred_at AND newer.id > legacy.id)
        )
  )
  AND NOT EXISTS (
      SELECT 1 FROM matching_response_events canonical
      WHERE canonical.idempotency_key = CONCAT('legacy-matching-response:', legacy.id)
  );

DROP TRIGGER IF EXISTS trg_matching_response_events_before_update;
CREATE TRIGGER trg_matching_response_events_before_update
BEFORE UPDATE ON matching_response_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_response_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_matching_response_events_before_delete;
CREATE TRIGGER trg_matching_response_events_before_delete
BEFORE DELETE ON matching_response_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_response_events records cannot be deleted';

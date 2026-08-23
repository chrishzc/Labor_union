-- File: 1002_customer_service_human_escalation.sql
-- Description: Customer Service HIGH escalation 與不可變事件的 additive schema。

-- M4-DB is additive only. It does not alter, seed, backfill, or remove any
-- existing Customer Service, LINE, anomaly, runtime, or scheduling object.
CREATE TABLE IF NOT EXISTS customer_service_escalations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_event_identity VARCHAR(191) NOT NULL,
    source_kind VARCHAR(64) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    trigger_code ENUM(
        'explicit_human_request',
        'explicit_wrong_answer',
        'binding_failure_threshold_2',
        'complaint',
        'runtime_critical'
    ) NOT NULL,
    trigger_policy_version VARCHAR(191) NOT NULL,
    ticket_id BIGINT NOT NULL,
    ticket_category ENUM(
        'service_flow',
        'payment_subsidy',
        'service_progress',
        'profile_update',
        'contact_union',
        'other'
    ) NOT NULL,
    urgency ENUM('high') NOT NULL DEFAULT 'high',
    workflow_status ENUM('open','claimed','handling','resolved') NOT NULL DEFAULT 'open',
    workflow_version BIGINT NOT NULL DEFAULT 0,
    hold_scope_ref VARCHAR(191) NOT NULL,
    automation_hold_state ENUM('active','released') NOT NULL DEFAULT 'active',
    hold_version BIGINT NOT NULL DEFAULT 0,
    actor_ref VARCHAR(191) NOT NULL,
    claim_at_utc DATETIME(6) NULL,
    handling_started_at_utc DATETIME(6) NULL,
    resolved_at_utc DATETIME(6) NULL,
    resolution_code VARCHAR(64) NULL,
    resolution_evidence_digest CHAR(64) NULL,
    masked_context JSON NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    masked_alert_intent_ref VARCHAR(191) NULL,
    delivery_task_ref VARCHAR(191) NULL,
    delivery_outcome_ref VARCHAR(191) NULL,
    alert_status ENUM('pending','queued','sent','failed','unknown') NOT NULL DEFAULT 'pending',
    active_hold_scope_key VARCHAR(191)
        GENERATED ALWAYS AS (
            CASE WHEN automation_hold_state = 'active' THEN hold_scope_ref ELSE NULL END
        ) STORED,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_customer_service_escalation_source (source_event_identity),
    UNIQUE KEY uq_customer_service_escalation_idempotency (idempotency_key),
    UNIQUE KEY uq_customer_service_escalation_active_scope (active_hold_scope_key),
    INDEX idx_customer_service_escalation_ticket (ticket_id, id),
    INDEX idx_customer_service_escalation_status_time (workflow_status, updated_at_utc),
    INDEX idx_customer_service_escalation_trigger_time (trigger_code, created_at_utc),
    CONSTRAINT fk_customer_service_escalation_ticket
        FOREIGN KEY (ticket_id) REFERENCES customer_service_tickets(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_customer_service_escalation_source_fingerprint
        CHECK (source_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_customer_service_escalation_source_kind
        CHECK (CHAR_LENGTH(TRIM(source_kind)) > 0),
    CONSTRAINT chk_customer_service_escalation_policy_version
        CHECK (CHAR_LENGTH(TRIM(trigger_policy_version)) > 0),
    CONSTRAINT chk_customer_service_escalation_scope
        CHECK (CHAR_LENGTH(TRIM(hold_scope_ref)) > 0),
    CONSTRAINT chk_customer_service_escalation_actor
        CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0),
    CONSTRAINT chk_customer_service_escalation_identities
        CHECK (
            CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        ),
    CONSTRAINT chk_customer_service_escalation_hold_state
        CHECK (
            (workflow_status = 'resolved' AND automation_hold_state = 'released')
            OR (workflow_status <> 'resolved' AND automation_hold_state = 'active')
        ),
    CONSTRAINT chk_customer_service_escalation_resolution
        CHECK (
            workflow_status <> 'resolved'
            OR (
                resolution_code IS NOT NULL
                AND resolution_evidence_digest IS NOT NULL
                AND
                CHAR_LENGTH(TRIM(resolution_code)) > 0
                AND resolution_evidence_digest REGEXP '^[0-9a-f]{64}$'
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customer_service_escalation_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    escalation_id BIGINT NOT NULL,
    event_type ENUM('created','claimed','handling_started','resolved','hold_released') NOT NULL,
    expected_escalation_version BIGINT NOT NULL,
    resulting_escalation_version BIGINT NOT NULL,
    expected_ticket_version BIGINT NULL,
    resulting_ticket_version BIGINT NULL,
    expected_hold_version BIGINT NOT NULL,
    resulting_hold_version BIGINT NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    reason_evidence_digest CHAR(64) NOT NULL,
    receipt_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_customer_service_escalation_event_receipt (receipt_id),
    UNIQUE KEY uq_customer_service_escalation_event_idempotency (idempotency_key),
    INDEX idx_customer_service_escalation_event_stream (escalation_id, id),
    INDEX idx_customer_service_escalation_event_type_time (event_type, created_at_utc),
    CONSTRAINT fk_customer_service_escalation_event_escalation
        FOREIGN KEY (escalation_id) REFERENCES customer_service_escalations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_customer_service_escalation_event_versions
        CHECK (
            resulting_escalation_version >= expected_escalation_version
            AND resulting_hold_version >= expected_hold_version
            AND (
                expected_ticket_version IS NULL
                OR resulting_ticket_version IS NOT NULL
            )
        ),
    CONSTRAINT chk_customer_service_escalation_event_actor
        CHECK (CHAR_LENGTH(TRIM(actor_ref)) > 0),
    CONSTRAINT chk_customer_service_escalation_event_reason
        CHECK (
            CHAR_LENGTH(TRIM(reason_code)) > 0
            AND reason_evidence_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_customer_service_escalation_event_identities
        CHECK (
            CHAR_LENGTH(TRIM(receipt_id)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_customer_service_escalation_events_before_update;
CREATE TRIGGER trg_customer_service_escalation_events_before_update
BEFORE UPDATE ON customer_service_escalation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'customer_service_escalation_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_customer_service_escalation_events_before_delete;
CREATE TRIGGER trg_customer_service_escalation_events_before_delete
BEFORE DELETE ON customer_service_escalation_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'customer_service_escalation_events records cannot be deleted';

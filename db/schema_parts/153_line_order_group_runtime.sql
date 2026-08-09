-- Canonical LINE order-group command, participant, and invitation runtime.

ALTER TABLE line_order_group_bindings
    MODIFY COLUMN binding_status ENUM(
        'unbound','bound','inviting','active','attention','replaced','released'
    ) NOT NULL DEFAULT 'unbound',
    ADD COLUMN last_invitation_at_utc DATETIME(6) NULL AFTER aggregate_version,
    ADD COLUMN activated_at_utc DATETIME(6) NULL AFTER last_invitation_at_utc;

CREATE TABLE IF NOT EXISTS line_order_group_participants (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    participant_type ENUM('customer','staff') NOT NULL,
    line_user_id VARCHAR(191) NOT NULL,
    invitation_status ENUM(
        'pending','sent','joined','left','failed'
    ) NOT NULL DEFAULT 'pending',
    joined_at_utc DATETIME(6) NULL,
    left_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_participant (
        case_no, participant_type, line_user_id
    ),
    INDEX idx_line_order_group_participant_user (line_user_id, case_no),
    CONSTRAINT fk_line_order_group_participant_binding
        FOREIGN KEY (case_no) REFERENCES line_order_group_bindings(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_order_group_runtime_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    event_type ENUM(
        'invitation_relayed','member_joined','member_left',
        'group_left','attention_required'
    ) NOT NULL,
    line_user_id VARCHAR(191) NULL,
    invitation_fingerprint CHAR(64) NULL,
    actor_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_runtime_idempotency (idempotency_key),
    INDEX idx_line_order_group_runtime_case (case_no, occurred_at_utc, id),
    CONSTRAINT fk_line_order_group_runtime_binding
        FOREIGN KEY (case_no) REFERENCES line_order_group_bindings(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_invitation_fingerprint CHECK (
        invitation_fingerprint IS NULL
        OR invitation_fingerprint REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_order_group_runtime_events_before_update;
CREATE TRIGGER trg_line_order_group_runtime_events_before_update
BEFORE UPDATE ON line_order_group_runtime_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_order_group_runtime_events_before_delete;
CREATE TRIGGER trg_line_order_group_runtime_events_before_delete
BEFORE DELETE ON line_order_group_runtime_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be deleted';

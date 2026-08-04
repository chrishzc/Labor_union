-- Additive Orders Terms, contract-flow, and irreversible service-lock facts.

ALTER TABLE orders
    ADD COLUMN staff_payment_due_date DATE NULL AFTER actual_end_date;

ALTER TABLE order_lifecycle_state_events
    ADD UNIQUE KEY uq_order_lifecycle_state_event_case_identity (
        id,
        case_no
    );

CREATE TABLE IF NOT EXISTS order_contract_flow_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    contract_identity VARCHAR(191) NOT NULL,
    event_type ENUM('contract_completed') NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_contract_completed_case (case_no, event_type),
    UNIQUE KEY uq_order_contract_event_idempotency (idempotency_key),
    CONSTRAINT fk_order_contract_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_contract_event_text
        CHECK (
            CHAR_LENGTH(TRIM(contract_identity)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_service_data_locks (
    case_no VARCHAR(50) PRIMARY KEY,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    client_settlement_fingerprint CHAR(64) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_service_data_lock_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_service_data_lock_lifecycle_event
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_service_data_lock_fingerprint
        CHECK (client_settlement_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_service_data_lock_actor
        CHECK (CHAR_LENGTH(TRIM(created_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_terms_change_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_terms JSON NOT NULL,
    after_terms JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_terms_change_idempotency (idempotency_key),
    CONSTRAINT fk_order_terms_change_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_terms_change_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_terms_change_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_terms_change_snapshots
        CHECK (
            JSON_TYPE(before_terms) = 'OBJECT'
            AND JSON_TYPE(after_terms) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS orders_domain_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'lifecycle_projection_changed',
        'service_data_locked',
        'anomaly_root_changed'
    ) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending', 'processing', 'delivered', 'failed')
        NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_orders_domain_outbox_intent (intent_key),
    INDEX idx_orders_domain_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_orders_domain_outbox_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_orders_domain_outbox_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_orders_domain_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_terms_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_terms_event_id BIGINT NOT NULL,
    scheduling_command_receipt_id BIGINT NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    scheduling_version BIGINT UNSIGNED NOT NULL,
    scheduling_generation INT UNSIGNED NOT NULL,
    client_finance_version BIGINT UNSIGNED NOT NULL,
    payroll_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    service_data_lock_formed TINYINT(1) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_terms_receipt_key (idempotency_key),
    CONSTRAINT fk_order_terms_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_terms_receipt_event
        FOREIGN KEY (order_terms_event_id)
        REFERENCES order_terms_change_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_terms_receipt_scheduling
        FOREIGN KEY (scheduling_command_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_terms_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_terms_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_terms_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_contract_flow_events_before_update;
CREATE TRIGGER trg_order_contract_flow_events_before_update
BEFORE UPDATE ON order_contract_flow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_contract_flow_events_before_delete;
CREATE TRIGGER trg_order_contract_flow_events_before_delete
BEFORE DELETE ON order_contract_flow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_service_data_locks_before_update;
CREATE TRIGGER trg_order_service_data_locks_before_update
BEFORE UPDATE ON order_service_data_locks
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_service_data_locks_before_delete;
CREATE TRIGGER trg_order_service_data_locks_before_delete
BEFORE DELETE ON order_service_data_locks
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_terms_change_events_before_update;
CREATE TRIGGER trg_order_terms_change_events_before_update
BEFORE UPDATE ON order_terms_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_terms_change_events_before_delete;
CREATE TRIGGER trg_order_terms_change_events_before_delete
BEFORE DELETE ON order_terms_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_terms_apply_receipts_before_update;
CREATE TRIGGER trg_order_terms_apply_receipts_before_update
BEFORE UPDATE ON order_terms_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_terms_apply_receipts_before_delete;
CREATE TRIGGER trg_order_terms_apply_receipts_before_delete
BEFORE DELETE ON order_terms_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be deleted';

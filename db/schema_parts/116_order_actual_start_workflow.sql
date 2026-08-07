-- Additive Actual Start root events and outer transaction receipts.

CREATE TABLE IF NOT EXISTS order_actual_start_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    event_type ENUM(
        'confirmed',
        'corrected',
        'reconfirmed_after_delayed_settlement'
    ) NOT NULL,
    before_actual_start_date DATE NULL,
    after_actual_start_date DATE NOT NULL,
    deposit_settlement_identity CHAR(64) NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_actual_start_event_idempotency (idempotency_key),
    UNIQUE KEY uq_order_actual_start_event_case_identity (id, case_no),
    CONSTRAINT fk_order_actual_start_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_actual_start_event_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_actual_start_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_actual_start_event_settlement
        CHECK (
            deposit_settlement_identity IS NULL
            OR deposit_settlement_identity REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_actual_start_event_shape
        CHECK (
            (
                event_type = 'confirmed'
                AND before_actual_start_date IS NULL
                AND deposit_settlement_identity IS NULL
            )
            OR
            (
                event_type = 'corrected'
                AND before_actual_start_date IS NOT NULL
                AND deposit_settlement_identity IS NULL
            )
            OR
            (
                event_type = 'reconfirmed_after_delayed_settlement'
                AND before_actual_start_date IS NOT NULL
                AND deposit_settlement_identity IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_actual_start_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    actual_start_event_id BIGINT NOT NULL,
    scheduling_command_receipt_id BIGINT NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    reconfirmation_control_event_id BIGINT UNSIGNED NULL,
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
    actual_start_date DATE NOT NULL,
    actual_end_date DATE NOT NULL,
    service_data_lock_formed TINYINT(1) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_actual_start_receipt_key (idempotency_key),
    CONSTRAINT fk_order_actual_start_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_event
        FOREIGN KEY (actual_start_event_id, case_no)
        REFERENCES order_actual_start_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_scheduling
        FOREIGN KEY (scheduling_command_receipt_id)
        REFERENCES scheduling_command_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_actual_start_receipt_control
        FOREIGN KEY (reconfirmation_control_event_id)
        REFERENCES order_lifecycle_control_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_actual_start_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_actual_start_receipt_dates
        CHECK (actual_end_date >= actual_start_date),
    CONSTRAINT chk_order_actual_start_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_actual_start_events_before_update;
CREATE TRIGGER trg_order_actual_start_events_before_update
BEFORE UPDATE ON order_actual_start_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_actual_start_events_before_delete;
CREATE TRIGGER trg_order_actual_start_events_before_delete
BEFORE DELETE ON order_actual_start_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_actual_start_receipts_before_update;
CREATE TRIGGER trg_order_actual_start_receipts_before_update
BEFORE UPDATE ON order_actual_start_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_actual_start_receipts_before_delete;
CREATE TRIGGER trg_order_actual_start_receipts_before_delete
BEFORE DELETE ON order_actual_start_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be deleted';

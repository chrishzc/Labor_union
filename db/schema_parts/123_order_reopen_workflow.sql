-- Additive immutable events and receipts for controlled order reopening.

CREATE TABLE IF NOT EXISTS order_reopen_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    cancellation_event_id BIGINT NOT NULL,
    before_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    after_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    expected_order_version BIGINT UNSIGNED NOT NULL,
    resulting_order_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_reopen_event_key (idempotency_key),
    UNIQUE KEY uq_order_reopen_event_owner (id, case_no),
    INDEX idx_order_reopen_cancellation (
        cancellation_event_id,
        case_no
    ),
    CONSTRAINT fk_order_reopen_event_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_event_cancellation
        FOREIGN KEY (cancellation_event_id, case_no)
        REFERENCES order_cancellation_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_reopen_event_version
        CHECK (resulting_order_version = expected_order_version + 1),
    CONSTRAINT chk_order_reopen_event_status
        CHECK (
            before_status = '訂單取消'
            AND after_status IN ('洽談中', '訂單成立', '服務中')
        ),
    CONSTRAINT chk_order_reopen_event_fingerprint
        CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_order_reopen_event_text
        CHECK (
            CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_reopen_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    reopen_event_id BIGINT NOT NULL,
    cancellation_control_event_id BIGINT UNSIGNED NOT NULL,
    lifecycle_event_id BIGINT UNSIGNED NOT NULL,
    cancellation_event_id BIGINT NOT NULL,
    order_version BIGINT UNSIGNED NOT NULL,
    lifecycle_status ENUM(
        '洽談中',
        '訂單成立',
        '服務中',
        '訂單完成',
        '訂單取消'
    ) NOT NULL,
    requires_fresh_scheduling_preview TINYINT(1) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_reopen_receipt_key (idempotency_key),
    CONSTRAINT fk_order_reopen_receipt_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_event
        FOREIGN KEY (reopen_event_id, case_no)
        REFERENCES order_reopen_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_control
        FOREIGN KEY (cancellation_control_event_id)
        REFERENCES order_lifecycle_control_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_lifecycle
        FOREIGN KEY (lifecycle_event_id, case_no)
        REFERENCES order_lifecycle_state_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_reopen_receipt_cancellation
        FOREIGN KEY (cancellation_event_id, case_no)
        REFERENCES order_cancellation_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_reopen_receipt_fingerprints
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_order_reopen_receipt_result
        CHECK (
            lifecycle_status IN ('洽談中', '訂單成立', '服務中')
            AND requires_fresh_scheduling_preview = 1
            AND JSON_TYPE(result_snapshot) = 'OBJECT'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_reopen_events_before_update;
CREATE TRIGGER trg_order_reopen_events_before_update
BEFORE UPDATE ON order_reopen_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_reopen_events_before_delete;
CREATE TRIGGER trg_order_reopen_events_before_delete
BEFORE DELETE ON order_reopen_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_order_reopen_receipts_before_update;
CREATE TRIGGER trg_order_reopen_receipts_before_update
BEFORE UPDATE ON order_reopen_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_reopen_receipts_before_delete;
CREATE TRIGGER trg_order_reopen_receipts_before_delete
BEFORE DELETE ON order_reopen_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be deleted';

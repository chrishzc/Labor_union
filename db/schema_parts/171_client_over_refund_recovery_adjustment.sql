-- Immutable authorized-adjustment evidence for client over-refund recovery.

ALTER TABLE client_over_refund_recoveries
    DROP CHECK chk_client_over_refund_amount;

ALTER TABLE client_over_refund_recoveries
    ADD CONSTRAINT chk_client_over_refund_amount
    CHECK (
        amount_due_ntd >= 0
        AND (
            (amount_due_ntd > 0 AND status IN ('open', 'partially_recovered'))
            OR (amount_due_ntd = 0 AND status IN ('recovered', 'adjusted'))
        )
    );

ALTER TABLE client_over_refund_recovery_events
    MODIFY COLUMN event_type ENUM(
        'established',
        'collected',
        'authorized_adjustment',
        'cancelled'
    ) NOT NULL;

ALTER TABLE client_over_refund_recovery_events
    DROP CHECK chk_client_over_refund_event_amount;

ALTER TABLE client_over_refund_recovery_events
    ADD CONSTRAINT chk_client_over_refund_event_amount
    CHECK (
        after_amount_ntd >= 0
        AND (
            (event_type = 'established' AND before_amount_ntd = 0 AND after_amount_ntd > 0)
            OR (event_type = 'collected' AND before_amount_ntd > after_amount_ntd)
            OR (event_type = 'authorized_adjustment' AND before_amount_ntd > after_amount_ntd)
            OR (event_type = 'cancelled' AND before_amount_ntd > after_amount_ntd)
        )
    );

CREATE TABLE IF NOT EXISTS client_over_refund_recovery_adjustment_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    recovery_identity VARCHAR(191) NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    remaining_after_ntd BIGINT NOT NULL,
    resulting_status ENUM('open', 'adjusted') NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_over_refund_adjustment_receipt_key (idempotency_key),
    CONSTRAINT fk_client_over_refund_adjustment_receipt_recovery
        FOREIGN KEY (recovery_identity)
        REFERENCES client_over_refund_recoveries(recovery_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_over_refund_adjustment_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_client_over_refund_adjustment_receipt_remaining
        CHECK (remaining_after_ntd >= 0),
    CONSTRAINT chk_client_over_refund_adjustment_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_over_refund_adjustment_receipts_before_update;
CREATE TRIGGER trg_client_over_refund_adjustment_receipts_before_update
BEFORE UPDATE ON client_over_refund_recovery_adjustment_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund adjustment receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_client_over_refund_adjustment_receipts_before_delete;
CREATE TRIGGER trg_client_over_refund_adjustment_receipts_before_delete
BEFORE DELETE ON client_over_refund_recovery_adjustment_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund adjustment receipts cannot be deleted';

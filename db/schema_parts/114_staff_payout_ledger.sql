-- Additive Staff Payables immutable payout/return/reversal ledger.

CREATE TABLE IF NOT EXISTS staff_payout_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    finance_import_row_id BIGINT NULL,
    event_type ENUM('payout', 'return', 'reversal') NOT NULL,
    amount_ntd BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    bank_account_identity_hash CHAR(64) NOT NULL,
    reversal_of_event_id BIGINT NULL,
    reconciliation_reference VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payout_import_row (finance_import_row_id),
    UNIQUE KEY uq_staff_payout_idempotency (idempotency_key),
    INDEX idx_staff_payout_staff_date (staff_id, occurred_on, id),
    CONSTRAINT fk_staff_payout_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_import_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_reversal
        FOREIGN KEY (reversal_of_event_id) REFERENCES staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payout_amount
        CHECK (amount_ntd > 0),
    CONSTRAINT chk_staff_payout_account_hash
        CHECK (bank_account_identity_hash REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_staff_payout_reversal_shape
        CHECK (
            (event_type = 'payout' AND reversal_of_event_id IS NULL)
            OR (
                event_type IN ('return', 'reversal')
                AND reversal_of_event_id IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payout_obligation_links (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    payout_event_id BIGINT NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    allocated_amount_ntd BIGINT NOT NULL,
    allocation_ordinal INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payout_obligation_link (
        payout_event_id,
        obligation_identity
    ),
    UNIQUE KEY uq_staff_payout_link_ordinal (
        payout_event_id,
        allocation_ordinal
    ),
    INDEX idx_staff_payout_link_obligation (
        obligation_identity,
        payout_event_id
    ),
    CONSTRAINT fk_staff_payout_link_event
        FOREIGN KEY (payout_event_id) REFERENCES staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payout_link_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payout_link_amount
        CHECK (allocated_amount_ntd > 0),
    CONSTRAINT chk_staff_payout_link_ordinal
        CHECK (allocation_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payable_accounts (
    staff_id INT PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_payable_account_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payable_projections (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    staff_id INT NOT NULL,
    obligation_amount_ntd BIGINT NOT NULL,
    net_paid_ntd BIGINT NOT NULL,
    balance_ntd BIGINT NOT NULL,
    status ENUM('payable', 'completed', 'anomaly') NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    current_event_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_staff_payable_projection_status (
        staff_id,
        status,
        obligation_identity
    ),
    CONSTRAINT fk_staff_payable_projection_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payable_projection_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_payable_projection_event
        FOREIGN KEY (current_event_id) REFERENCES staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payable_projection_money
        CHECK (
            obligation_amount_ntd > 0
            AND net_paid_ntd >= 0
            AND balance_ntd = obligation_amount_ntd - net_paid_ntd
        ),
    CONSTRAINT chk_staff_payable_projection_status
        CHECK (
            (
                status = 'payable'
                AND net_paid_ntd = 0
                AND balance_ntd = obligation_amount_ntd
            )
            OR (
                status = 'completed'
                AND net_paid_ntd = obligation_amount_ntd
                AND balance_ntd = 0
            )
            OR (
                status = 'anomaly'
                AND net_paid_ntd <> 0
                AND balance_ntd <> 0
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payables_apply_receipts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    staff_id INT NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_payables_receipt_idempotency (idempotency_key),
    CONSTRAINT fk_staff_payables_receipt_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payables_receipt_fingerprint
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_staff_payables_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_payables_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM(
        'payable_projection_refresh',
        'payout_anomaly_required'
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
    UNIQUE KEY uq_staff_payables_outbox_intent (intent_key),
    INDEX idx_staff_payables_outbox_delivery (
        status,
        next_attempt_at,
        id
    ),
    CONSTRAINT fk_staff_payables_outbox_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_payables_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_staff_payout_events_before_update;
CREATE TRIGGER trg_staff_payout_events_before_update
BEFORE UPDATE ON staff_payout_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_events_before_delete;
CREATE TRIGGER trg_staff_payout_events_before_delete
BEFORE DELETE ON staff_payout_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payout_links_before_update;
CREATE TRIGGER trg_staff_payout_links_before_update
BEFORE UPDATE ON staff_payout_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payout_links_before_delete;
CREATE TRIGGER trg_staff_payout_links_before_delete
BEFORE DELETE ON staff_payout_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_payables_receipts_before_update;
CREATE TRIGGER trg_staff_payables_receipts_before_update
BEFORE UPDATE ON staff_payables_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_staff_payables_receipts_before_delete;
CREATE TRIGGER trg_staff_payables_receipts_before_delete
BEFORE DELETE ON staff_payables_apply_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be deleted';

-- File: 1020_historical_owner_payment_settlement.sql
-- Description: Owner-specific historical payment evidence and settlement overlays.
-- Additive only; no seed, backfill, existing-row rewrite, or bank-ledger fabrication.

CREATE TABLE IF NOT EXISTS historical_client_payment_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    direction ENUM('receivable_from_client','payable_to_client') NOT NULL,
    confirmation_kind ENUM('paid','settled') NOT NULL,
    payer_role ENUM('client','union') NOT NULL,
    payee_role ENUM('client','union') NOT NULL,
    payment_date DATE NULL,
    payment_date_unknown_reason VARCHAR(500) NULL,
    source_availability ENUM('missing','ambiguous','unrecoverable') NOT NULL,
    evidence_reference VARCHAR(191) NULL,
    historical_adoption_receipt_id BIGINT UNSIGNED NOT NULL,
    expected_account_version BIGINT UNSIGNED NOT NULL,
    resulting_account_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_client_payment_event_identity (event_identity),
    UNIQUE KEY uq_historical_client_payment_event_idempotency (idempotency_key),
    INDEX idx_historical_client_payment_case (case_no, id),
    CONSTRAINT fk_historical_client_payment_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_client_payment_adoption
        FOREIGN KEY (historical_adoption_receipt_id)
        REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_client_payment_version
        CHECK (resulting_account_version = expected_account_version + 1),
    CONSTRAINT chk_historical_client_payment_direction
        CHECK (
            (direction = 'receivable_from_client' AND payer_role = 'client' AND payee_role = 'union')
            OR
            (direction = 'payable_to_client' AND payer_role = 'union' AND payee_role = 'client')
        ),
    CONSTRAINT chk_historical_client_payment_date
        CHECK (
            (payment_date IS NOT NULL AND payment_date_unknown_reason IS NULL)
            OR
            (payment_date IS NULL AND CHAR_LENGTH(TRIM(payment_date_unknown_reason)) > 0)
        ),
    CONSTRAINT chk_historical_client_payment_text
        CHECK (
            CHAR_LENGTH(TRIM(event_identity)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(actor_id)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_client_payment_obligation_links (
    event_id BIGINT UNSIGNED NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    amount_snapshot_ntd BIGINT NOT NULL,
    obligation_type ENUM('deposit','first','second','refund','subsidy_return','adjustment') NOT NULL,
    obligation_direction ENUM('receivable_from_client','payable_to_client') NOT NULL,
    obligation_projection_version BIGINT UNSIGNED NOT NULL,
    link_ordinal INT UNSIGNED NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id, obligation_identity),
    UNIQUE KEY uq_historical_client_payment_link_ordinal (event_id, link_ordinal),
    INDEX idx_historical_client_payment_link_obligation (obligation_identity, event_id),
    CONSTRAINT fk_historical_client_payment_link_event
        FOREIGN KEY (event_id) REFERENCES historical_client_payment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_client_payment_link_obligation
        FOREIGN KEY (obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_client_payment_link_amount CHECK (amount_snapshot_ntd > 0),
    CONSTRAINT chk_historical_client_payment_link_ordinal CHECK (link_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_client_payment_projections (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    current_event_id BIGINT UNSIGNED NOT NULL,
    confirmation_kind ENUM('paid','settled') NOT NULL,
    amount_snapshot_ntd BIGINT NOT NULL,
    obligation_projection_version BIGINT UNSIGNED NOT NULL,
    account_version BIGINT UNSIGNED NOT NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_historical_client_payment_projection_case (case_no, obligation_identity),
    CONSTRAINT fk_historical_client_payment_projection_obligation
        FOREIGN KEY (obligation_identity) REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_client_payment_projection_event
        FOREIGN KEY (current_event_id) REFERENCES historical_client_payment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_client_payment_projection_amount CHECK (amount_snapshot_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_client_payment_source_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending','processing','delivered','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_client_payment_outbox_intent (intent_key),
    INDEX idx_historical_client_payment_outbox_delivery (status, next_attempt_at, id),
    CONSTRAINT fk_historical_client_payment_outbox_event
        FOREIGN KEY (event_id) REFERENCES historical_client_payment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_client_payment_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_staff_payout_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    confirmation_kind ENUM('paid','settled') NOT NULL,
    payer_role ENUM('union') NOT NULL,
    payee_role ENUM('staff') NOT NULL,
    payment_date DATE NULL,
    payment_date_unknown_reason VARCHAR(500) NULL,
    source_availability ENUM('missing','ambiguous','unrecoverable') NOT NULL,
    evidence_reference VARCHAR(191) NULL,
    historical_adoption_receipt_id BIGINT UNSIGNED NOT NULL,
    expected_staff_payables_version BIGINT UNSIGNED NOT NULL,
    resulting_staff_payables_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_staff_payout_event_identity (event_identity),
    UNIQUE KEY uq_historical_staff_payout_event_idempotency (idempotency_key),
    INDEX idx_historical_staff_payout_case_staff (case_no, staff_id, id),
    CONSTRAINT fk_historical_staff_payout_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_staff_payout_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_staff_payout_adoption
        FOREIGN KEY (historical_adoption_receipt_id)
        REFERENCES historical_order_adoption_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_staff_payout_version
        CHECK (resulting_staff_payables_version = expected_staff_payables_version + 1),
    CONSTRAINT chk_historical_staff_payout_date
        CHECK (
            (payment_date IS NOT NULL AND payment_date_unknown_reason IS NULL)
            OR
            (payment_date IS NULL AND CHAR_LENGTH(TRIM(payment_date_unknown_reason)) > 0)
        ),
    CONSTRAINT chk_historical_staff_payout_text
        CHECK (
            CHAR_LENGTH(TRIM(event_identity)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(actor_id)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_staff_payout_obligation_links (
    event_id BIGINT UNSIGNED NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    amount_snapshot_ntd BIGINT NOT NULL,
    obligation_payroll_version BIGINT UNSIGNED NOT NULL,
    link_ordinal INT UNSIGNED NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id, obligation_identity),
    UNIQUE KEY uq_historical_staff_payout_link_ordinal (event_id, link_ordinal),
    INDEX idx_historical_staff_payout_link_obligation (obligation_identity, event_id),
    CONSTRAINT fk_historical_staff_payout_link_event
        FOREIGN KEY (event_id) REFERENCES historical_staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_staff_payout_link_obligation
        FOREIGN KEY (obligation_identity) REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_staff_payout_link_amount CHECK (amount_snapshot_ntd > 0),
    CONSTRAINT chk_historical_staff_payout_link_ordinal CHECK (link_ordinal > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_staff_payout_projections (
    obligation_identity VARCHAR(191) PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    staff_id INT NOT NULL,
    current_event_id BIGINT UNSIGNED NOT NULL,
    confirmation_kind ENUM('paid','settled') NOT NULL,
    amount_snapshot_ntd BIGINT NOT NULL,
    obligation_payroll_version BIGINT UNSIGNED NOT NULL,
    staff_payables_version BIGINT UNSIGNED NOT NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_historical_staff_payout_projection_case (case_no, staff_id, obligation_identity),
    CONSTRAINT fk_historical_staff_payout_projection_obligation
        FOREIGN KEY (obligation_identity) REFERENCES staff_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_staff_payout_projection_event
        FOREIGN KEY (current_event_id) REFERENCES historical_staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_staff_payout_projection_amount CHECK (amount_snapshot_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_staff_payout_source_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    status ENUM('pending','processing','delivered','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    delivered_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_staff_payout_outbox_intent (intent_key),
    INDEX idx_historical_staff_payout_outbox_delivery (status, next_attempt_at, id),
    CONSTRAINT fk_historical_staff_payout_outbox_event
        FOREIGN KEY (event_id) REFERENCES historical_staff_payout_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_staff_payout_outbox_payload
        CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_client_payment_events_before_update;
CREATE TRIGGER trg_historical_client_payment_events_before_update
BEFORE UPDATE ON historical_client_payment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_client_payment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_client_payment_events_before_delete;
CREATE TRIGGER trg_historical_client_payment_events_before_delete
BEFORE DELETE ON historical_client_payment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_client_payment_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_client_payment_links_before_update;
CREATE TRIGGER trg_historical_client_payment_links_before_update
BEFORE UPDATE ON historical_client_payment_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_client_payment_obligation_links records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_client_payment_links_before_delete;
CREATE TRIGGER trg_historical_client_payment_links_before_delete
BEFORE DELETE ON historical_client_payment_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_client_payment_obligation_links records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_staff_payout_events_before_update;
CREATE TRIGGER trg_historical_staff_payout_events_before_update
BEFORE UPDATE ON historical_staff_payout_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_staff_payout_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_staff_payout_events_before_delete;
CREATE TRIGGER trg_historical_staff_payout_events_before_delete
BEFORE DELETE ON historical_staff_payout_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_staff_payout_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_historical_staff_payout_links_before_update;
CREATE TRIGGER trg_historical_staff_payout_links_before_update
BEFORE UPDATE ON historical_staff_payout_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_staff_payout_obligation_links records cannot be updated';

DROP TRIGGER IF EXISTS trg_historical_staff_payout_links_before_delete;
CREATE TRIGGER trg_historical_staff_payout_links_before_delete
BEFORE DELETE ON historical_staff_payout_obligation_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_staff_payout_obligation_links records cannot be deleted';

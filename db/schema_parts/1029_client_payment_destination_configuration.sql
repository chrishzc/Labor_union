CREATE TABLE IF NOT EXISTS client_payment_destination_configuration_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    expected_revision BIGINT NOT NULL,
    resulting_revision BIGINT NOT NULL,
    account_display VARCHAR(255) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_client_payment_destination_event_idempotency (idempotency_key),
    UNIQUE KEY uq_client_payment_destination_event_revision (resulting_revision),
    CONSTRAINT chk_client_payment_destination_event_revision CHECK (resulting_revision = expected_revision + 1),
    CONSTRAINT chk_client_payment_destination_event_text CHECK (
        CHAR_LENGTH(TRIM(account_display)) > 0 AND CHAR_LENGTH(TRIM(actor)) > 0
        AND CHAR_LENGTH(TRIM(reason)) > 0 AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    ),
    CONSTRAINT chk_client_payment_destination_event_fingerprint CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_payment_destination_configuration_current (
    singleton_id TINYINT PRIMARY KEY,
    current_event_id BIGINT NOT NULL,
    account_display VARCHAR(255) NOT NULL,
    revision BIGINT NOT NULL,
    UNIQUE KEY uq_client_payment_destination_current_event (current_event_id),
    CONSTRAINT fk_client_payment_destination_current_event FOREIGN KEY (current_event_id)
        REFERENCES client_payment_destination_configuration_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_payment_destination_singleton CHECK (singleton_id = 1),
    CONSTRAINT chk_client_payment_destination_current_text CHECK (CHAR_LENGTH(TRIM(account_display)) > 0),
    CONSTRAINT chk_client_payment_destination_current_revision CHECK (revision > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_payment_destination_configuration_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    event_id BIGINT NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_client_payment_destination_receipt_event (event_id),
    CONSTRAINT fk_client_payment_destination_receipt_event FOREIGN KEY (event_id)
        REFERENCES client_payment_destination_configuration_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_payment_destination_receipt_fingerprint CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_client_payment_destination_receipt_snapshot CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_payment_destination_events_before_update;
CREATE TRIGGER trg_client_payment_destination_events_before_update
BEFORE UPDATE ON client_payment_destination_configuration_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination events are immutable';

DROP TRIGGER IF EXISTS trg_client_payment_destination_events_before_delete;
CREATE TRIGGER trg_client_payment_destination_events_before_delete
BEFORE DELETE ON client_payment_destination_configuration_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination events are immutable';

DROP TRIGGER IF EXISTS trg_client_payment_destination_receipts_before_update;
CREATE TRIGGER trg_client_payment_destination_receipts_before_update
BEFORE UPDATE ON client_payment_destination_configuration_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination receipts are immutable';

DROP TRIGGER IF EXISTS trg_client_payment_destination_receipts_before_delete;
CREATE TRIGGER trg_client_payment_destination_receipts_before_delete
BEFORE DELETE ON client_payment_destination_configuration_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination receipts are immutable';

-- File: 1036_registry_owner_mutations.sql
-- Description: Preserve-data additive bridge for Issue #276 client/staff registry mutations.
-- Data effect: schema_only; existing business rows are preserved and no values are inferred.

ALTER TABLE `staff`
    ADD COLUMN `staff_profile_version` BIGINT UNSIGNED NOT NULL DEFAULT 0
        AFTER `admin_notes`;

-- Fail closed if preserved rows already contain a reused full account number.
-- The unique index is the serialization boundary for concurrent cross-Staff adds.
ALTER TABLE `staff_bank_accounts`
    ADD UNIQUE KEY `uq_staff_bank_accounts_account_no` (`account_no`);

ALTER TABLE `staff_bank_accounts`
    ADD COLUMN `is_active` BOOLEAN NOT NULL DEFAULT TRUE AFTER `is_primary`;

CREATE TABLE IF NOT EXISTS client_profile_admin_change_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_values_json JSON NOT NULL,
    after_values_json JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_client_profile_admin_event_key (idempotency_key),
    UNIQUE KEY uq_client_profile_admin_event_version (client_id, resulting_version),
    CONSTRAINT fk_client_profile_admin_event_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_profile_admin_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_client_profile_admin_event_payload
        CHECK (JSON_TYPE(before_values_json) = 'OBJECT' AND JSON_TYPE(after_values_json) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_record_correction_states (
    beclass_record_id INT NOT NULL PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    effective_values_json JSON NOT NULL,
    updated_by VARCHAR(191) NOT NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_beclass_correction_state_record FOREIGN KEY (beclass_record_id)
        REFERENCES beclass_records(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_correction_state_payload
        CHECK (JSON_TYPE(effective_values_json) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS beclass_record_correction_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    beclass_record_id INT NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_values_json JSON NOT NULL,
    after_values_json JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_beclass_correction_event_key (idempotency_key),
    UNIQUE KEY uq_beclass_correction_event_version (beclass_record_id, resulting_version),
    CONSTRAINT fk_beclass_correction_event_record FOREIGN KEY (beclass_record_id)
        REFERENCES beclass_records(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_beclass_correction_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_beclass_correction_event_payload
        CHECK (JSON_TYPE(before_values_json) = 'OBJECT' AND JSON_TYPE(after_values_json) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_profile_change_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_values_json JSON NOT NULL,
    after_values_json JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_profile_event_key (idempotency_key),
    UNIQUE KEY uq_staff_profile_event_version (staff_id, resulting_version),
    CONSTRAINT fk_staff_profile_event_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_profile_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_staff_profile_event_payload
        CHECK (JSON_TYPE(before_values_json) = 'OBJECT' AND JSON_TYPE(after_values_json) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_bank_account_states (
    staff_id INT NOT NULL PRIMARY KEY,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_by VARCHAR(191) NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_bank_state_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_bank_account_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    account_id INT NOT NULL,
    operation ENUM('add','replace','deactivate','set_primary') NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    bank_code VARCHAR(10) NULL,
    branch_code VARCHAR(10) NULL,
    account_last4 CHAR(4) NULL,
    was_primary BOOLEAN NOT NULL,
    is_primary BOOLEAN NOT NULL,
    was_active BOOLEAN NOT NULL,
    is_active BOOLEAN NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_staff_bank_event_key (idempotency_key),
    UNIQUE KEY uq_staff_bank_event_version (staff_id, resulting_version),
    CONSTRAINT fk_staff_bank_event_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_bank_event_account FOREIGN KEY (account_id)
        REFERENCES staff_bank_accounts(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_staff_bank_event_version
        CHECK (resulting_version = expected_version + 1),
    CONSTRAINT chk_staff_bank_event_last4
        CHECK (account_last4 IS NULL OR account_last4 REGEXP '^[0-9]{4}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_profile_admin_change_events_before_update;
CREATE TRIGGER trg_client_profile_admin_change_events_before_update
BEFORE UPDATE ON client_profile_admin_change_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client profile admin events cannot be updated';
DROP TRIGGER IF EXISTS trg_client_profile_admin_change_events_before_delete;
CREATE TRIGGER trg_client_profile_admin_change_events_before_delete
BEFORE DELETE ON client_profile_admin_change_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client profile admin events cannot be deleted';

DROP TRIGGER IF EXISTS trg_beclass_record_correction_events_before_update;
CREATE TRIGGER trg_beclass_record_correction_events_before_update
BEFORE UPDATE ON beclass_record_correction_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'beclass correction events cannot be updated';
DROP TRIGGER IF EXISTS trg_beclass_record_correction_events_before_delete;
CREATE TRIGGER trg_beclass_record_correction_events_before_delete
BEFORE DELETE ON beclass_record_correction_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'beclass correction events cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_profile_change_events_before_update;
CREATE TRIGGER trg_staff_profile_change_events_before_update
BEFORE UPDATE ON staff_profile_change_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff profile events cannot be updated';
DROP TRIGGER IF EXISTS trg_staff_profile_change_events_before_delete;
CREATE TRIGGER trg_staff_profile_change_events_before_delete
BEFORE DELETE ON staff_profile_change_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff profile events cannot be deleted';

DROP TRIGGER IF EXISTS trg_staff_bank_account_events_before_update;
CREATE TRIGGER trg_staff_bank_account_events_before_update
BEFORE UPDATE ON staff_bank_account_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff bank account events cannot be updated';
DROP TRIGGER IF EXISTS trg_staff_bank_account_events_before_delete;
CREATE TRIGGER trg_staff_bank_account_events_before_delete
BEFORE DELETE ON staff_bank_account_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff bank account events cannot be deleted';

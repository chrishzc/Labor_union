-- Global transactional mutex for idempotent application commands.

CREATE TABLE IF NOT EXISTS application_command_claims (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_family VARCHAR(100) NOT NULL,
    aggregate_identity VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_application_command_claim_text
        CHECK (
            CHAR_LENGTH(TRIM(command_family)) > 0
            AND CHAR_LENGTH(TRIM(aggregate_identity)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        ),
    CONSTRAINT chk_application_command_claim_fingerprint
        CHECK (command_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_application_command_claims_before_update;
CREATE TRIGGER trg_application_command_claims_before_update
BEFORE UPDATE ON application_command_claims
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be updated';

DROP TRIGGER IF EXISTS trg_application_command_claims_before_delete;
CREATE TRIGGER trg_application_command_claims_before_delete
BEFORE DELETE ON application_command_claims
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be deleted';

-- Verified external contract evidence; Integration never mutates Orders.

CREATE TABLE IF NOT EXISTS contract_webhook_security_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    canonical_payload_hash CHAR(64) NOT NULL,
    signature_verified BOOLEAN NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    received_at_utc DATETIME(6) NOT NULL,
    INDEX idx_contract_security_received (provider, received_at_utc),
    CONSTRAINT chk_contract_security_hash CHECK (canonical_payload_hash REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_provider_mappings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    provider_contract_id VARCHAR(191) NOT NULL,
    internal_contract_identity VARCHAR(191) NOT NULL,
    mapping_status ENUM('active','retired') NOT NULL DEFAULT 'active',
    version INT UNSIGNED NOT NULL DEFAULT 0,
    mapped_by_actor_id VARCHAR(191) NOT NULL,
    mapped_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_provider_mapping (provider, provider_contract_id),
    INDEX idx_contract_internal_identity (internal_contract_identity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_webhook_inbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    provider_event_id VARCHAR(191) NOT NULL,
    provider_contract_id VARCHAR(191) NOT NULL,
    provider_event_type VARCHAR(100) NOT NULL,
    provider_contract_status ENUM('pending_signature','signed','declined','cancelled','provider_failed') NOT NULL,
    provider_occurred_at_utc DATETIME(6) NOT NULL,
    canonical_payload_hash CHAR(64) NOT NULL,
    minimal_payload_json JSON NOT NULL,
    processing_status ENUM('received','verified','normalized','applied','rejected','retry_pending','failed') NOT NULL DEFAULT 'received',
    processing_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    available_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(191) NULL,
    received_at_utc DATETIME(6) NOT NULL,
    applied_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_contract_provider_event (provider, provider_event_id),
    INDEX idx_contract_inbox_claim (processing_status, available_at_utc, id),
    INDEX idx_contract_inbox_contract (provider, provider_contract_id, id),
    CONSTRAINT chk_contract_inbox_hash CHECK (canonical_payload_hash REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_contract_inbox_payload CHECK (JSON_TYPE(minimal_payload_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_mapping_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    mapping_id BIGINT UNSIGNED NOT NULL,
    provider VARCHAR(50) NOT NULL,
    provider_contract_id VARCHAR(191) NOT NULL,
    internal_contract_identity VARCHAR(191) NOT NULL,
    resulting_version INT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_mapping_event_key (idempotency_key),
    INDEX idx_contract_mapping_event_mapping (mapping_id, occurred_at_utc),
    CONSTRAINT fk_contract_mapping_event_mapping FOREIGN KEY (mapping_id)
        REFERENCES contract_provider_mappings(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_mapping_fingerprint CHECK (payload_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS external_contract_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    inbox_id BIGINT UNSIGNED NOT NULL,
    provider VARCHAR(50) NOT NULL,
    provider_event_id VARCHAR(191) NOT NULL,
    provider_contract_id VARCHAR(191) NOT NULL,
    internal_contract_identity VARCHAR(191) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    contract_status ENUM('pending_signature','signed','declined','cancelled','provider_failed') NOT NULL,
    canonical_payload_hash CHAR(64) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    recorded_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_external_contract_inbox (inbox_id),
    UNIQUE KEY uq_external_contract_event (provider, provider_event_id),
    INDEX idx_external_contract_identity (internal_contract_identity, recorded_at_utc),
    CONSTRAINT fk_external_contract_inbox FOREIGN KEY (inbox_id)
        REFERENCES contract_webhook_inbox(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_evidence_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    external_event_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(100) NOT NULL DEFAULT 'ContractCompletionEvidenceAvailable',
    aggregate_identity VARCHAR(191) NOT NULL,
    payload_snapshot JSON NOT NULL,
    processing_status ENUM('pending','processing','completed','retry_pending','failed') NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_evidence_outbox_key (idempotency_key),
    INDEX idx_contract_evidence_outbox_status (processing_status, id),
    CONSTRAINT fk_contract_evidence_event FOREIGN KEY (external_event_id)
        REFERENCES external_contract_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_evidence_payload CHECK (JSON_TYPE(payload_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_external_contract_events_before_update;
CREATE TRIGGER trg_external_contract_events_before_update
BEFORE UPDATE ON external_contract_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='external_contract_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_external_contract_events_before_delete;
CREATE TRIGGER trg_external_contract_events_before_delete
BEFORE DELETE ON external_contract_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='external_contract_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_contract_mapping_events_before_update;
CREATE TRIGGER trg_contract_mapping_events_before_update
BEFORE UPDATE ON contract_mapping_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='contract_mapping_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_mapping_events_before_delete;
CREATE TRIGGER trg_contract_mapping_events_before_delete
BEFORE DELETE ON contract_mapping_events FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='contract_mapping_events records cannot be deleted';

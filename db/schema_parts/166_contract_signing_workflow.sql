-- 166_contract_signing_workflow.sql
-- 案件契約文件、月嫂／客戶簽署事件與簽約前服務承諾。
-- 文件與事件均 append-only；訂單 lifecycle、正式排班與金流各自維持既有 SSOT。

CREATE TABLE IF NOT EXISTS contract_document_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    document_scope ENUM('staff_segment', 'client_contract') NOT NULL,
    document_role ENUM('template_generated', 'signed_return') NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    matching_segment_id BIGINT NULL,
    document_target_key VARCHAR(100) NOT NULL,
    source_document_version_id BIGINT NULL,
    template_key VARCHAR(100) NULL,
    template_sha256 CHAR(64) NULL,
    mapping_sha256 CHAR(64) NULL,
    facts_snapshot_sha256 CHAR(64) NULL,
    media_asset_id BIGINT NOT NULL,
    version_number INT NOT NULL,
    replaces_document_version_id BIGINT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_document_version (
        case_no, document_scope, document_target_key, version_number
    ),
    INDEX idx_contract_document_case (case_no, document_scope, created_at),
    INDEX idx_contract_document_segment (matching_segment_id, created_at),
    CONSTRAINT fk_contract_document_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_plan
        FOREIGN KEY (matching_plan_id) REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_segment
        FOREIGN KEY (matching_segment_id) REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_source
        FOREIGN KEY (source_document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_media_asset
        FOREIGN KEY (media_asset_id) REFERENCES media_assets(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_replaces
        FOREIGN KEY (replaces_document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_document_target
        CHECK (
            (document_scope = 'staff_segment'
             AND matching_segment_id IS NOT NULL
             AND CHAR_LENGTH(TRIM(document_target_key)) > 0)
            OR (document_scope = 'client_contract'
                AND matching_segment_id IS NULL
                AND CHAR_LENGTH(TRIM(document_target_key)) > 0)
        ),
    CONSTRAINT chk_contract_document_source
        CHECK (
            (document_role = 'template_generated'
             AND template_key IS NOT NULL
             AND template_sha256 IS NOT NULL
             AND mapping_sha256 IS NOT NULL
             AND facts_snapshot_sha256 IS NOT NULL
             AND source_document_version_id IS NULL)
            OR (document_role = 'signed_return' AND source_document_version_id IS NOT NULL)
        ),
    CONSTRAINT chk_contract_document_version
        CHECK (version_number >= 1 AND CHAR_LENGTH(TRIM(created_by)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_document_access_grants (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    document_version_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    recipient_line_user_id VARCHAR(191) NOT NULL,
    recipient_subject_type ENUM('customer', 'staff') NOT NULL,
    recipient_subject_reference VARCHAR(191) NOT NULL,
    token_sha256 CHAR(64) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_document_access_token (token_sha256),
    INDEX idx_contract_document_access_document (
        document_version_id, recipient_line_user_id, expires_at
    ),
    CONSTRAINT fk_contract_document_access_document
        FOREIGN KEY (document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_document_access_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_document_access_text
        CHECK (
            CHAR_LENGTH(TRIM(recipient_line_user_id)) > 0
            AND CHAR_LENGTH(TRIM(recipient_subject_reference)) > 0
            AND CHAR_LENGTH(TRIM(created_by)) > 0
        ),
    CONSTRAINT chk_contract_document_access_token
        CHECK (token_sha256 REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_signing_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    document_version_id BIGINT NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    matching_segment_id BIGINT NULL,
    event_type ENUM('sent', 'signed_received') NOT NULL,
    delivery_channel ENUM('line') NULL,
    line_delivery_task_id BIGINT UNSIGNED NULL,
    document_access_grant_id BIGINT UNSIGNED NULL,
    event_key VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_signing_event_key (event_key),
    INDEX idx_contract_signing_event_case (case_no, occurred_at),
    INDEX idx_contract_signing_event_document (document_version_id, occurred_at),
    INDEX idx_contract_signing_event_segment (matching_segment_id, occurred_at),
    CONSTRAINT fk_contract_signing_event_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_document
        FOREIGN KEY (document_version_id) REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_plan
        FOREIGN KEY (matching_plan_id) REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_segment
        FOREIGN KEY (matching_segment_id) REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_line_delivery_task
        FOREIGN KEY (line_delivery_task_id) REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_signing_event_document_access_grant
        FOREIGN KEY (document_access_grant_id)
        REFERENCES contract_document_access_grants(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_signing_event_channel
        CHECK (
            (event_type = 'sent' AND delivery_channel = 'line'
             AND line_delivery_task_id IS NOT NULL
             AND document_access_grant_id IS NOT NULL)
            OR (event_type = 'signed_received' AND delivery_channel IS NULL
                AND line_delivery_task_id IS NULL
                AND document_access_grant_id IS NULL)
        ),
    CONSTRAINT chk_contract_signing_event_payload
        CHECK (
            JSON_TYPE(payload) = 'OBJECT'
            AND CHAR_LENGTH(TRIM(event_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_signing_command_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    command_kind VARCHAR(80) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    document_version_id BIGINT NULL,
    signing_event_id BIGINT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_signing_receipt_key (idempotency_key),
    CONSTRAINT fk_contract_signing_receipt_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_contract_signing_receipt_document FOREIGN KEY (document_version_id) REFERENCES contract_document_versions(id),
    CONSTRAINT fk_contract_signing_receipt_event FOREIGN KEY (signing_event_id) REFERENCES contract_signing_events(id),
    CONSTRAINT chk_contract_signing_receipt_payload CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_signing_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    signing_event_id BIGINT NOT NULL,
    intent_key VARCHAR(100) NOT NULL,
    intent_type VARCHAR(80) NOT NULL,
    payload_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contract_signing_outbox_key (intent_key),
    CONSTRAINT fk_contract_signing_outbox_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_contract_signing_outbox_event FOREIGN KEY (signing_event_id) REFERENCES contract_signing_events(id),
    CONSTRAINT chk_contract_signing_outbox_payload CHECK (JSON_TYPE(payload_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precontract_service_commitments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    commitment_key VARCHAR(100) NOT NULL,
    plan_snapshot_sha256 CHAR(64) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_precontract_commitment_key (commitment_key),
    UNIQUE KEY uq_precontract_commitment_plan (matching_plan_id),
    INDEX idx_precontract_commitment_case (case_no, created_at),
    CONSTRAINT fk_precontract_commitment_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_precontract_commitment_plan
        FOREIGN KEY (matching_plan_id) REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_precontract_commitment_nonempty
        CHECK (
            CHAR_LENGTH(TRIM(commitment_key)) > 0
            AND CHAR_LENGTH(TRIM(created_by)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precontract_service_commitment_days (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    commitment_id BIGINT NOT NULL,
    matching_segment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_precontract_commitment_segment_date (
        commitment_id, matching_segment_id, service_date
    ),
    INDEX idx_precontract_commitment_staff_date (staff_id, service_date),
    CONSTRAINT fk_precontract_commitment_day_header
        FOREIGN KEY (commitment_id) REFERENCES precontract_service_commitments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_precontract_commitment_day_segment
        FOREIGN KEY (matching_segment_id) REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_precontract_commitment_day_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precontract_service_commitment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    commitment_id BIGINT NOT NULL,
    event_type ENUM('cancelled', 'converted') NOT NULL,
    event_key VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_precontract_commitment_event_key (event_key),
    UNIQUE KEY uq_precontract_commitment_terminal (commitment_id),
    CONSTRAINT fk_precontract_commitment_event_header
        FOREIGN KEY (commitment_id) REFERENCES precontract_service_commitments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_precontract_commitment_event_payload
        CHECK (
            JSON_TYPE(payload) = 'OBJECT'
            AND CHAR_LENGTH(TRIM(event_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_contract_document_versions_before_update;
CREATE TRIGGER trg_contract_document_versions_before_update BEFORE UPDATE ON contract_document_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_document_versions records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_document_versions_before_delete;
CREATE TRIGGER trg_contract_document_versions_before_delete BEFORE DELETE ON contract_document_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_document_versions records cannot be deleted';

DROP TRIGGER IF EXISTS trg_contract_signing_events_before_update;
CREATE TRIGGER trg_contract_signing_events_before_update BEFORE UPDATE ON contract_signing_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_signing_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_signing_events_before_delete;
CREATE TRIGGER trg_contract_signing_events_before_delete BEFORE DELETE ON contract_signing_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_signing_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_precontract_service_commitments_before_update;
CREATE TRIGGER trg_precontract_service_commitments_before_update BEFORE UPDATE ON precontract_service_commitments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitments records cannot be updated';

DROP TRIGGER IF EXISTS trg_precontract_service_commitments_before_delete;
CREATE TRIGGER trg_precontract_service_commitments_before_delete BEFORE DELETE ON precontract_service_commitments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitments records cannot be deleted';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_days_before_update;
CREATE TRIGGER trg_precontract_service_commitment_days_before_update BEFORE UPDATE ON precontract_service_commitment_days FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_days records cannot be updated';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_days_before_delete;
CREATE TRIGGER trg_precontract_service_commitment_days_before_delete BEFORE DELETE ON precontract_service_commitment_days FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_days records cannot be deleted';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_events_before_update;
CREATE TRIGGER trg_precontract_service_commitment_events_before_update BEFORE UPDATE ON precontract_service_commitment_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_precontract_service_commitment_events_before_delete;
CREATE TRIGGER trg_precontract_service_commitment_events_before_delete BEFORE DELETE ON precontract_service_commitment_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_events records cannot be deleted';

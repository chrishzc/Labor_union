-- File: 1005_contract_external_signing_successor.sql
-- Description: 建立外部平台簽署 session、完成回報、最終 PDF recovery、文件連結與 closed receipts。

ALTER TABLE controlled_file_staging_objects
    MODIFY COLUMN purpose ENUM(
        'unsigned_contract', 'final_signed_contract', 'service_date_confirmation',
        'baby_log_photo', 'meal_photo', 'order_notice', 'staff_resume',
        'staff_certificate', 'staff_health_exam', 'rich_menu_background'
    ) NOT NULL,
    DROP CHECK chk_controlled_file_staging_owner_purpose,
    ADD CONSTRAINT chk_controlled_file_staging_owner_purpose CHECK (
        (owner_type = 'contract_signing'
            AND purpose IN ('unsigned_contract', 'final_signed_contract'))
        OR (owner_type = 'scheduling' AND purpose IN (
            'service_date_confirmation', 'baby_log_photo', 'meal_photo'
        ))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN (
            'staff_resume', 'staff_certificate', 'staff_health_exam'
        ))
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    );

ALTER TABLE controlled_file_objects
    DROP FOREIGN KEY fk_controlled_file_object_supersedes;

ALTER TABLE controlled_file_objects
    MODIFY COLUMN purpose ENUM(
        'unsigned_contract', 'final_signed_contract', 'service_date_confirmation',
        'baby_log_photo', 'meal_photo', 'order_notice', 'staff_resume',
        'staff_certificate', 'staff_health_exam', 'rich_menu_background'
    ) NOT NULL,
    DROP CHECK chk_controlled_file_object_owner_purpose,
    ADD CONSTRAINT chk_controlled_file_object_owner_purpose CHECK (
        (owner_type = 'contract_signing'
            AND purpose IN ('unsigned_contract', 'final_signed_contract'))
        OR (owner_type = 'scheduling' AND purpose IN (
            'service_date_confirmation', 'baby_log_photo', 'meal_photo'
        ))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN (
            'staff_resume', 'staff_certificate', 'staff_health_exam'
        ))
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    );

ALTER TABLE controlled_file_objects
    ADD CONSTRAINT fk_controlled_file_object_supersedes FOREIGN KEY (
        supersedes_object_id, owner_type, subject_reference, object_key,
        purpose, supersedes_version_number
    ) REFERENCES controlled_file_objects (
        id, owner_type, subject_reference, object_key, purpose, version_number
    )
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS contract_external_signing_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    external_signing_session_id VARCHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    matching_plan_id BIGINT NOT NULL,
    current_document_set_sha256 CHAR(64) NOT NULL,
    commitment_id BIGINT NULL,
    client_reminder_task_id BIGINT UNSIGNED NULL,
    session_state ENUM(
        'staff_reporting', 'staff_reports_complete',
        'client_reported_final_pdf_pending', 'completed', 'superseded'
    ) NOT NULL DEFAULT 'staff_reporting',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    active_case_key VARCHAR(50) GENERATED ALWAYS AS (
        CASE WHEN session_state = 'superseded' THEN NULL ELSE case_no END
    ) STORED,
    activated_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_external_session_id (external_signing_session_id),
    UNIQUE KEY uq_contract_external_active_case (active_case_key),
    INDEX idx_contract_external_session_case (case_no, id),
    INDEX idx_contract_external_session_plan (matching_plan_id, id),
    INDEX idx_contract_external_session_state (session_state, updated_at_utc, id),
    CONSTRAINT fk_contract_external_session_case FOREIGN KEY (case_no)
        REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_session_plan FOREIGN KEY (matching_plan_id)
        REFERENCES caregiver_matching_plans(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_session_commitment FOREIGN KEY (commitment_id)
        REFERENCES precontract_service_commitments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_session_reminder FOREIGN KEY (client_reminder_task_id)
        REFERENCES line_delivery_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_external_session_identity CHECK (
        external_signing_session_id REGEXP '^ces_[0-9a-f]{32}$'
        AND current_document_set_sha256 REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(activated_by_actor)) > 0
    ),
    CONSTRAINT chk_contract_external_session_state CHECK (
        (session_state = 'staff_reporting'
            AND commitment_id IS NULL AND client_reminder_task_id IS NULL)
        OR (session_state IN ('staff_reports_complete',
                'client_reported_final_pdf_pending', 'completed')
            AND commitment_id IS NOT NULL AND client_reminder_task_id IS NOT NULL)
        OR session_state = 'superseded'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_external_completion_reports (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    report_id VARCHAR(64) NOT NULL,
    external_signing_session_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    report_scope ENUM('staff', 'client') NOT NULL,
    matching_segment_id BIGINT NULL,
    document_version_id BIGINT NOT NULL,
    commitment_id BIGINT NULL,
    reporter_subject_type ENUM('staff', 'customer') NOT NULL,
    reporter_subject_reference VARCHAR(191) NOT NULL,
    source_kind ENUM('verified_line', 'manual_attested') NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_payload_sha256 CHAR(64) NOT NULL,
    line_inbox_event_id BIGINT UNSIGNED NULL,
    verified_line_user_id VARCHAR(191) NULL,
    verified_binding_version BIGINT UNSIGNED NULL,
    manual_confirmation_method VARCHAR(100) NULL,
    manual_reason VARCHAR(1000) NULL,
    manual_evidence_reference VARCHAR(191) NULL,
    manual_evidence_sha256 CHAR(64) NULL,
    target_identity VARCHAR(191) GENERATED ALWAYS AS (
        CONCAT(report_scope, ':', COALESCE(CAST(matching_segment_id AS CHAR), 'client'))
    ) STORED,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    expected_status_version BIGINT UNSIGNED NOT NULL,
    resulting_status_version BIGINT UNSIGNED NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_external_report_id (report_id),
    UNIQUE KEY uq_contract_external_report_source (source_event_identity),
    UNIQUE KEY uq_contract_external_report_idempotency (idempotency_key),
    UNIQUE KEY uq_contract_external_report_target (
        external_signing_session_id, target_identity
    ),
    INDEX idx_contract_external_report_case (case_no, id),
    INDEX idx_contract_external_report_document (document_version_id, id),
    INDEX idx_contract_external_report_segment (matching_segment_id, id),
    CONSTRAINT fk_contract_external_report_session FOREIGN KEY (
        external_signing_session_id
    ) REFERENCES contract_external_signing_sessions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_report_case FOREIGN KEY (case_no)
        REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_report_segment FOREIGN KEY (matching_segment_id)
        REFERENCES caregiver_matching_plan_segments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_report_document FOREIGN KEY (document_version_id)
        REFERENCES contract_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_report_commitment FOREIGN KEY (commitment_id)
        REFERENCES precontract_service_commitments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_report_inbox FOREIGN KEY (line_inbox_event_id)
        REFERENCES line_inbox_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_report_binding FOREIGN KEY (verified_line_user_id)
        REFERENCES line_identity_bindings(line_user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_external_report_identity CHECK (
        report_id REGEXP '^cer_[0-9a-f]{32}$'
        AND source_payload_sha256 REGEXP '^[0-9a-f]{64}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND CHAR_LENGTH(TRIM(source_event_identity)) > 0
        AND CHAR_LENGTH(TRIM(reporter_subject_reference)) > 0
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND resulting_status_version = expected_status_version + 1
    ),
    CONSTRAINT chk_contract_external_report_target CHECK (
        (report_scope = 'staff' AND matching_segment_id IS NOT NULL
            AND commitment_id IS NULL AND reporter_subject_type = 'staff')
        OR (report_scope = 'client' AND matching_segment_id IS NULL
            AND commitment_id IS NOT NULL AND reporter_subject_type = 'customer')
    ),
    CONSTRAINT chk_contract_external_report_source CHECK (
        (source_kind = 'verified_line'
            AND line_inbox_event_id IS NOT NULL
            AND verified_line_user_id IS NOT NULL
            AND verified_binding_version IS NOT NULL
            AND manual_confirmation_method IS NULL
            AND manual_reason IS NULL
            AND manual_evidence_reference IS NULL
            AND manual_evidence_sha256 IS NULL)
        OR (source_kind = 'manual_attested'
            AND line_inbox_event_id IS NULL
            AND verified_line_user_id IS NULL
            AND verified_binding_version IS NULL
            AND manual_confirmation_method IS NOT NULL
            AND manual_reason IS NOT NULL
            AND manual_evidence_reference IS NOT NULL
            AND manual_evidence_sha256 IS NOT NULL
            AND CHAR_LENGTH(TRIM(manual_confirmation_method)) > 0
            AND CHAR_LENGTH(TRIM(manual_reason)) > 0
            AND CHAR_LENGTH(TRIM(manual_evidence_reference)) > 0
            AND manual_evidence_sha256 REGEXP '^[0-9a-f]{64}$')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_final_pdf_recovery_tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    recovery_task_id VARCHAR(64) NOT NULL,
    external_signing_session_id BIGINT UNSIGNED NOT NULL,
    client_report_id BIGINT UNSIGNED NOT NULL,
    task_state ENUM('pending', 'fulfilled', 'superseded') NOT NULL DEFAULT 'pending',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    created_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    fulfilled_at_utc DATETIME(6) NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_final_recovery_id (recovery_task_id),
    UNIQUE KEY uq_contract_final_recovery_report (client_report_id),
    UNIQUE KEY uq_contract_final_recovery_idempotency (idempotency_key),
    INDEX idx_contract_final_recovery_session (external_signing_session_id, id),
    INDEX idx_contract_final_recovery_state (task_state, created_at_utc, id),
    CONSTRAINT fk_contract_final_recovery_session FOREIGN KEY (
        external_signing_session_id
    ) REFERENCES contract_external_signing_sessions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_final_recovery_report FOREIGN KEY (client_report_id)
        REFERENCES contract_external_completion_reports(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_final_recovery_identity CHECK (
        recovery_task_id REGEXP '^cfrt_[0-9a-f]{32}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(created_by_actor)) > 0
    ),
    CONSTRAINT chk_contract_final_recovery_state CHECK (
        (task_state = 'fulfilled' AND fulfilled_at_utc IS NOT NULL)
        OR (task_state IN ('pending', 'superseded') AND fulfilled_at_utc IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_final_document_versions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    final_document_id VARCHAR(64) NOT NULL,
    external_signing_session_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    source_document_set_sha256 CHAR(64) NOT NULL,
    controlled_file_object_id BIGINT UNSIGNED NOT NULL,
    version_number BIGINT UNSIGNED NOT NULL,
    contract_identity VARCHAR(191) NOT NULL,
    content_type ENUM('application/pdf') NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    created_by_actor VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_final_document_id (final_document_id),
    UNIQUE KEY uq_contract_final_document_session (external_signing_session_id),
    UNIQUE KEY uq_contract_final_document_object (controlled_file_object_id),
    UNIQUE KEY uq_contract_final_document_case_version (case_no, version_number),
    INDEX idx_contract_final_document_case (case_no, id),
    CONSTRAINT fk_contract_final_document_session FOREIGN KEY (
        external_signing_session_id
    ) REFERENCES contract_external_signing_sessions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_final_document_case FOREIGN KEY (case_no)
        REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_final_document_object FOREIGN KEY (controlled_file_object_id)
        REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_final_document_identity CHECK (
        final_document_id REGEXP '^cfd_[0-9a-f]{32}$'
        AND source_document_set_sha256 REGEXP '^[0-9a-f]{64}$'
        AND content_sha256 REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(contract_identity)) > 0
        AND CHAR_LENGTH(TRIM(created_by_actor)) > 0
        AND version_number > 0
        AND size_bytes > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contract_external_signing_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    receipt_id VARCHAR(64) NOT NULL,
    external_signing_session_id BIGINT UNSIGNED NOT NULL,
    command_type ENUM(
        'record_staff_report', 'record_client_report', 'apply_final_signed_contract'
    ) NOT NULL,
    schema_version ENUM('contract-external-signing-receipt.v1') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NULL,
    expected_status_version BIGINT UNSIGNED NOT NULL,
    result_status_version BIGINT UNSIGNED NOT NULL,
    completion_report_id BIGINT UNSIGNED NULL,
    final_document_version_id BIGINT UNSIGNED NULL,
    result_snapshot JSON NOT NULL,
    outcome_state ENUM('recorded', 'completed') NOT NULL,
    actor_ref VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    applied_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_contract_external_receipt_id (receipt_id),
    UNIQUE KEY uq_contract_external_receipt_idempotency (idempotency_key),
    INDEX idx_contract_external_receipt_session (external_signing_session_id, id),
    INDEX idx_contract_external_receipt_report (completion_report_id, id),
    INDEX idx_contract_external_receipt_document (final_document_version_id, id),
    CONSTRAINT fk_contract_external_receipt_session FOREIGN KEY (
        external_signing_session_id
    ) REFERENCES contract_external_signing_sessions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_receipt_report FOREIGN KEY (completion_report_id)
        REFERENCES contract_external_completion_reports(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_contract_external_receipt_document FOREIGN KEY (
        final_document_version_id
    ) REFERENCES contract_final_document_versions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_contract_external_receipt_identity CHECK (
        receipt_id REGEXP '^cesr_[0-9a-f]{32}$'
        AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND CHAR_LENGTH(TRIM(actor_ref)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        AND result_status_version = expected_status_version + 1
    ),
    CONSTRAINT chk_contract_external_receipt_target CHECK (
        (command_type IN ('record_staff_report', 'record_client_report')
            AND completion_report_id IS NOT NULL
            AND final_document_version_id IS NULL
            AND preview_fingerprint IS NULL
            AND outcome_state = 'recorded')
        OR (command_type = 'apply_final_signed_contract'
            AND completion_report_id IS NULL
            AND final_document_version_id IS NOT NULL
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND outcome_state = 'completed')
    ),
    CONSTRAINT chk_contract_external_receipt_result CHECK (
        JSON_TYPE(result_snapshot) = 'OBJECT' AND JSON_LENGTH(result_snapshot) > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_contract_external_reports_before_update;
CREATE TRIGGER trg_contract_external_reports_before_update BEFORE UPDATE ON contract_external_completion_reports FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_completion_reports records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_external_reports_before_delete;
CREATE TRIGGER trg_contract_external_reports_before_delete BEFORE DELETE ON contract_external_completion_reports FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_completion_reports records cannot be deleted';

DROP TRIGGER IF EXISTS trg_contract_final_documents_before_update;
CREATE TRIGGER trg_contract_final_documents_before_update BEFORE UPDATE ON contract_final_document_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_final_document_versions records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_final_documents_before_delete;
CREATE TRIGGER trg_contract_final_documents_before_delete BEFORE DELETE ON contract_final_document_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_final_document_versions records cannot be deleted';

DROP TRIGGER IF EXISTS trg_contract_external_receipts_before_update;
CREATE TRIGGER trg_contract_external_receipts_before_update BEFORE UPDATE ON contract_external_signing_receipts FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_signing_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_contract_external_receipts_before_delete;
CREATE TRIGGER trg_contract_external_receipts_before_delete BEFORE DELETE ON contract_external_signing_receipts FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_signing_receipts records cannot be deleted';

-- File: 1021_task96_owner_contract_successors.sql
-- Purpose: additive persistence for the Task 96 owner contracts approved on 2026-08-31.
-- Data effect: schema only.  Existing business rows are neither inferred nor rewritten.

ALTER TABLE clients
    ADD COLUMN client_profile_version BIGINT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE client_profile_change_requests
    MODIFY COLUMN status ENUM(
        'pending','approved','approved_applied','partially_approved','rejected','reverted'
    ) NOT NULL DEFAULT 'pending',
    ADD COLUMN request_version BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER status,
    ADD COLUMN client_profile_version BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER request_version,
    ADD COLUMN reason VARCHAR(500) NULL AFTER old_values_json,
    ADD COLUMN idempotency_key VARCHAR(191) NULL AFTER reason,
    ADD COLUMN preview_fingerprint CHAR(64) NULL AFTER idempotency_key,
    ADD COLUMN command_fingerprint CHAR(64) NULL AFTER preview_fingerprint,
    ADD COLUMN correlation_id VARCHAR(191) NULL AFTER command_fingerprint,
    ADD COLUMN review_reason VARCHAR(500) NULL AFTER rejection_reason,
    ADD UNIQUE KEY uq_client_profile_change_request_idempotency (idempotency_key),
    ADD CONSTRAINT chk_client_profile_change_request_fingerprints CHECK (
        (preview_fingerprint IS NULL OR preview_fingerprint REGEXP '^[0-9a-f]{64}$')
        AND (command_fingerprint IS NULL OR command_fingerprint REGEXP '^[0-9a-f]{64}$')
    );

CREATE TABLE IF NOT EXISTS client_profile_change_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT NOT NULL,
    client_id INT NOT NULL,
    event_type ENUM('approved_applied','rejected') NOT NULL,
    resulting_profile_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    before_values_json JSON NOT NULL,
    after_values_json JSON NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_profile_change_event_key (idempotency_key),
    INDEX idx_client_profile_change_event_request (request_id,id),
    CONSTRAINT fk_client_profile_change_event_request FOREIGN KEY (request_id)
        REFERENCES client_profile_change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_profile_change_event_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_profile_change_event_payload CHECK (
        JSON_TYPE(before_values_json)='OBJECT' AND JSON_TYPE(after_values_json)='OBJECT'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_profile_change_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_client_profile_change_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_client_profile_change_receipt_result CHECK (JSON_TYPE(result_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_profile_change_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT NOT NULL,
    event_type ENUM('client_profile.approved') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    payload_json JSON NOT NULL,
    status ENUM('pending','processing','delivered','failed') NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at_utc DATETIME NULL,
    last_error_code VARCHAR(100) NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_profile_change_outbox_key (idempotency_key,event_type),
    INDEX idx_client_profile_change_outbox_due (status,next_attempt_at_utc,id),
    CONSTRAINT fk_client_profile_change_outbox_request FOREIGN KEY (request_id)
        REFERENCES client_profile_change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_profile_change_outbox_payload CHECK (JSON_TYPE(payload_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_import_pairing_accepted_lineages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    original_review_identity VARCHAR(191) NOT NULL,
    accepted_source_event_identity VARCHAR(191) NOT NULL,
    accepted_result_identity VARCHAR(191) NOT NULL,
    accepted_root_id INT NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_case_pairing_lineage_original (original_review_identity),
    UNIQUE KEY uq_case_pairing_lineage_source (accepted_source_event_identity),
    UNIQUE KEY uq_case_pairing_lineage_result (accepted_result_identity),
    CONSTRAINT fk_case_pairing_lineage_review FOREIGN KEY (original_review_identity)
        REFERENCES beclass_import_review_rows(review_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_case_pairing_lineage_root FOREIGN KEY (accepted_root_id)
        REFERENCES beclass_records(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_import_source_correction_lineages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    original_batch_id BIGINT NOT NULL,
    original_batch_identity VARCHAR(191) NOT NULL,
    original_batch_version BIGINT UNSIGNED NOT NULL,
    corrected_successor_batch_id BIGINT NOT NULL,
    corrected_successor_batch_identity VARCHAR(191) NOT NULL,
    corrected_successor_batch_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(191) NOT NULL,
    accepted_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_import_source_correction_original (original_batch_id,original_batch_version),
    UNIQUE KEY uq_finance_import_source_correction_successor (corrected_successor_batch_id),
    UNIQUE KEY uq_finance_import_source_correction_original_identity (original_batch_identity,original_batch_version),
    UNIQUE KEY uq_finance_import_source_correction_successor_identity (corrected_successor_batch_identity,corrected_successor_batch_version),
    CONSTRAINT fk_finance_import_source_correction_original FOREIGN KEY (original_batch_id)
        REFERENCES finance_import_batches(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_import_source_correction_successor FOREIGN KEY (corrected_successor_batch_id)
        REFERENCES finance_import_batches(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_import_source_correction_distinct CHECK (original_batch_id<>corrected_successor_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payroll_late_obligation_dispositions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    correction_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    obligation_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    disposition ENUM('increase_obligation','reduce_unpaid_obligation','correct_paid_obligation','reviewed_no_change') NOT NULL,
    before_amount_ntd BIGINT NOT NULL,
    corrected_amount_ntd BIGINT NOT NULL,
    delta_amount_ntd BIGINT NOT NULL,
    recovery_amount_ntd BIGINT NOT NULL DEFAULT 0,
    expected_payroll_version BIGINT UNSIGNED NOT NULL,
    resulting_payroll_version BIGINT UNSIGNED NOT NULL,
    expected_obligation_version BIGINT UNSIGNED NOT NULL,
    resulting_obligation_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payroll_late_disposition_identity (correction_identity),
    UNIQUE KEY uq_payroll_late_disposition_source (obligation_identity,source_event_identity),
    UNIQUE KEY uq_payroll_late_disposition_key (idempotency_key),
    INDEX idx_payroll_late_disposition_case (case_no,id),
    CONSTRAINT fk_payroll_late_disposition_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_late_disposition_obligation FOREIGN KEY (obligation_identity)
        REFERENCES staff_obligations(obligation_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_late_disposition_assignment FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_late_disposition_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payroll_late_disposition_versions CHECK (
        resulting_payroll_version=expected_payroll_version+1
        AND resulting_obligation_version=expected_obligation_version+1
    ),
    CONSTRAINT chk_payroll_late_disposition_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE staff_overpayment_recoveries
    ADD COLUMN payroll_correction_identity VARCHAR(191) NULL AFTER recovery_identity,
    ADD UNIQUE KEY uq_staff_overpayment_payroll_correction (payroll_correction_identity);

CREATE TABLE IF NOT EXISTS government_subsidy_integrity_rebuild_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    expected_owner_version BIGINT UNSIGNED NOT NULL,
    resulting_owner_version BIGINT UNSIGNED NOT NULL,
    source_snapshot_token VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_integrity_rebuild_key (idempotency_key),
    INDEX idx_government_integrity_rebuild_batch (batch_id,id),
    CONSTRAINT fk_government_integrity_rebuild_batch FOREIGN KEY (batch_id)
        REFERENCES government_subsidy_batch_accounts(batch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_integrity_rebuild_version CHECK (resulting_owner_version=expected_owner_version+1),
    CONSTRAINT chk_government_integrity_rebuild_fingerprint CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_claim_correction_lineages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    original_claim_item_id BIGINT NOT NULL,
    original_batch_id BIGINT NOT NULL,
    correction_path ENUM('draft_revision','submitted_correction') NOT NULL,
    scheduling_snapshot_identity VARCHAR(191) NOT NULL,
    scheduling_snapshot_version BIGINT UNSIGNED NOT NULL,
    scheduling_snapshot_token VARCHAR(191) NOT NULL,
    successor_revision_identity VARCHAR(191) NOT NULL,
    financial_consequence_reference VARCHAR(191) NULL,
    expected_owner_version BIGINT UNSIGNED NOT NULL,
    resulting_owner_version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_claim_correction_snapshot (
        original_claim_item_id,scheduling_snapshot_identity,scheduling_snapshot_version
    ),
    UNIQUE KEY uq_government_claim_correction_successor (successor_revision_identity),
    UNIQUE KEY uq_government_claim_correction_key (idempotency_key),
    CONSTRAINT fk_government_claim_correction_item FOREIGN KEY (original_claim_item_id,original_batch_id)
        REFERENCES subsidy_claim_batch_items(id,batch_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_claim_correction_version CHECK (resulting_owner_version=expected_owner_version+1),
    CONSTRAINT chk_government_claim_correction_fingerprint CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_recoveries (
    recovery_identity VARCHAR(191) PRIMARY KEY,
    source_outgoing_bank_fact_identity VARCHAR(191) NOT NULL,
    original_return_obligation_identity VARCHAR(191) NOT NULL,
    lawful_amount_ntd BIGINT NOT NULL,
    actual_amount_ntd BIGINT NOT NULL,
    excess_amount_ntd BIGINT NOT NULL,
    remaining_excess_ntd BIGINT NOT NULL,
    government_payer_identity VARCHAR(191) NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('open','partially_reconciled','reconciled') NOT NULL DEFAULT 'open',
    actor VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    receipt_reference VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_recovery_outgoing_fact (source_outgoing_bank_fact_identity),
    UNIQUE KEY uq_government_recovery_key (idempotency_key),
    CONSTRAINT chk_government_recovery_amounts CHECK (
        lawful_amount_ntd>=0 AND actual_amount_ntd>lawful_amount_ntd
        AND excess_amount_ntd=actual_amount_ntd-lawful_amount_ntd
        AND remaining_excess_ntd>=0 AND remaining_excess_ntd<=excess_amount_ntd
    ),
    CONSTRAINT chk_government_recovery_status CHECK (
        (status='open' AND remaining_excess_ntd=excess_amount_ntd)
        OR (status='partially_reconciled' AND remaining_excess_ntd>0 AND remaining_excess_ntd<excess_amount_ntd)
        OR (status='reconciled' AND remaining_excess_ntd=0)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_recovery_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recovery_identity VARCHAR(191) NOT NULL,
    incoming_bank_fact_identity VARCHAR(191) NOT NULL,
    amount_ntd BIGINT NOT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    resulting_status ENUM('partially_reconciled','reconciled') NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_recovery_event_bank_fact (incoming_bank_fact_identity),
    UNIQUE KEY uq_government_recovery_event_key (idempotency_key),
    INDEX idx_government_recovery_event_root (recovery_identity,id),
    CONSTRAINT fk_government_recovery_event_root FOREIGN KEY (recovery_identity)
        REFERENCES government_subsidy_recoveries(recovery_identity) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_recovery_event_amount CHECK (
        amount_ntd>0 AND before_remaining_ntd>0
        AND after_remaining_ntd=before_remaining_ntd-amount_ntd AND after_remaining_ntd>=0
    ),
    CONSTRAINT chk_government_recovery_event_version CHECK (resulting_version=expected_version+1),
    CONSTRAINT chk_government_recovery_event_fingerprint CHECK (preview_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_anomaly_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    operation_type ENUM('integrity_rebuild','claim_correction','recovery_create','recovery_reconcile') NOT NULL,
    subject_identity VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_government_anomaly_receipt_fingerprints CHECK (
        command_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_government_anomaly_receipt_result CHECK (JSON_TYPE(result_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_profile_change_events_before_update;
CREATE TRIGGER trg_client_profile_change_events_before_update BEFORE UPDATE ON client_profile_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client profile change events cannot be updated';
DROP TRIGGER IF EXISTS trg_client_profile_change_events_before_delete;
CREATE TRIGGER trg_client_profile_change_events_before_delete BEFORE DELETE ON client_profile_change_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client profile change events cannot be deleted';
DROP TRIGGER IF EXISTS trg_case_pairing_lineages_before_update;
CREATE TRIGGER trg_case_pairing_lineages_before_update BEFORE UPDATE ON case_import_pairing_accepted_lineages
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='case import pairing lineages cannot be updated';
DROP TRIGGER IF EXISTS trg_case_pairing_lineages_before_delete;
CREATE TRIGGER trg_case_pairing_lineages_before_delete BEFORE DELETE ON case_import_pairing_accepted_lineages
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='case import pairing lineages cannot be deleted';
DROP TRIGGER IF EXISTS trg_finance_source_correction_before_update;
CREATE TRIGGER trg_finance_source_correction_before_update BEFORE UPDATE ON finance_import_source_correction_lineages
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='finance import source correction lineages cannot be updated';
DROP TRIGGER IF EXISTS trg_finance_source_correction_before_delete;
CREATE TRIGGER trg_finance_source_correction_before_delete BEFORE DELETE ON finance_import_source_correction_lineages
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='finance import source correction lineages cannot be deleted';
DROP TRIGGER IF EXISTS trg_payroll_late_dispositions_before_update;
CREATE TRIGGER trg_payroll_late_dispositions_before_update BEFORE UPDATE ON payroll_late_obligation_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='payroll late obligation dispositions cannot be updated';
DROP TRIGGER IF EXISTS trg_payroll_late_dispositions_before_delete;
CREATE TRIGGER trg_payroll_late_dispositions_before_delete BEFORE DELETE ON payroll_late_obligation_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='payroll late obligation dispositions cannot be deleted';
DROP TRIGGER IF EXISTS trg_government_integrity_rebuild_before_update;
CREATE TRIGGER trg_government_integrity_rebuild_before_update BEFORE UPDATE ON government_subsidy_integrity_rebuild_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='government subsidy integrity rebuild events cannot be updated';
DROP TRIGGER IF EXISTS trg_government_integrity_rebuild_before_delete;
CREATE TRIGGER trg_government_integrity_rebuild_before_delete BEFORE DELETE ON government_subsidy_integrity_rebuild_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='government subsidy integrity rebuild events cannot be deleted';
DROP TRIGGER IF EXISTS trg_government_claim_correction_before_update;
CREATE TRIGGER trg_government_claim_correction_before_update BEFORE UPDATE ON government_subsidy_claim_correction_lineages
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='government subsidy claim correction lineages cannot be updated';
DROP TRIGGER IF EXISTS trg_government_claim_correction_before_delete;
CREATE TRIGGER trg_government_claim_correction_before_delete BEFORE DELETE ON government_subsidy_claim_correction_lineages
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='government subsidy claim correction lineages cannot be deleted';
DROP TRIGGER IF EXISTS trg_government_recovery_events_before_update;
CREATE TRIGGER trg_government_recovery_events_before_update BEFORE UPDATE ON government_subsidy_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='government subsidy recovery events cannot be updated';
DROP TRIGGER IF EXISTS trg_government_recovery_events_before_delete;
CREATE TRIGGER trg_government_recovery_events_before_delete BEFORE DELETE ON government_subsidy_recovery_events
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='government subsidy recovery events cannot be deleted';

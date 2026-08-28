-- File: 1009_anomaly_reclassification_disposition.sql
-- Description: 保存異常必要性移轉的不可變處分、receipt 與 bounded batch 證據。

CREATE TABLE IF NOT EXISTS anomaly_reclassification_dispositions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    disposition_identity VARCHAR(191) NOT NULL,
    alert_fingerprint CHAR(64) NOT NULL,
    definition_code VARCHAR(191) NOT NULL,
    disposition ENUM(
        'reclassified_to_owner_work_item',
        'retired_false_positive',
        'replaced_by_successor'
    ) NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    expected_workflow_version BIGINT UNSIGNED NOT NULL,
    target_domain VARCHAR(100) NULL,
    target_reference VARCHAR(191) NULL,
    target_version BIGINT UNSIGNED NULL,
    actor VARCHAR(255) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    rulebook_reference VARCHAR(500) NULL,
    release_evidence_reference VARCHAR(500) NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_anomaly_reclassification_disposition_identity (
        disposition_identity
    ),
    UNIQUE KEY uq_anomaly_reclassification_disposition_idempotency (
        idempotency_key
    ),
    UNIQUE KEY uq_anomaly_reclassification_disposition_alert (
        alert_fingerprint
    ),
    INDEX idx_anomaly_reclassification_disposition_source (
        definition_code,
        source_identity,
        source_version
    ),
    CONSTRAINT fk_anomaly_reclassification_disposition_alert
        FOREIGN KEY (alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_anomaly_reclassification_disposition_fingerprints
        CHECK (
            alert_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_anomaly_reclassification_disposition_target
        CHECK (
            (
                disposition = 'retired_false_positive'
                AND target_domain IS NULL
                AND target_reference IS NULL
                AND target_version IS NULL
            )
            OR (
                disposition IN (
                    'reclassified_to_owner_work_item',
                    'replaced_by_successor'
                )
                AND CHAR_LENGTH(TRIM(target_domain)) > 0
                AND CHAR_LENGTH(TRIM(target_reference)) > 0
                AND target_version IS NOT NULL
            )
        ),
    CONSTRAINT chk_anomaly_reclassification_disposition_retired_evidence
        CHECK (
            (
                disposition = 'retired_false_positive'
                AND CHAR_LENGTH(TRIM(rulebook_reference)) > 0
                AND CHAR_LENGTH(TRIM(release_evidence_reference)) > 0
            )
            OR disposition <> 'retired_false_positive'
        ),
    CONSTRAINT chk_anomaly_reclassification_disposition_optional_evidence
        CHECK (
            (
                (rulebook_reference IS NULL AND release_evidence_reference IS NULL)
                OR (
                    rulebook_reference IS NOT NULL
                    AND release_evidence_reference IS NOT NULL
                    AND CHAR_LENGTH(TRIM(rulebook_reference)) > 0
                    AND CHAR_LENGTH(TRIM(release_evidence_reference)) > 0
                )
            )
        ),
    CONSTRAINT chk_anomaly_reclassification_disposition_text
        CHECK (
            CHAR_LENGTH(TRIM(disposition_identity)) > 0
            AND CHAR_LENGTH(TRIM(definition_code)) > 0
            AND CHAR_LENGTH(TRIM(source_identity)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
            AND CHAR_LENGTH(TRIM(evidence_reference)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_reclassification_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_identity VARCHAR(191) NOT NULL,
    disposition_id BIGINT UNSIGNED NOT NULL,
    workflow_event_id BIGINT NOT NULL,
    before_state_fingerprint CHAR(64) NOT NULL,
    after_state_fingerprint CHAR(64) NOT NULL,
    before_workflow_version BIGINT UNSIGNED NOT NULL,
    after_workflow_version BIGINT UNSIGNED NOT NULL,
    result_snapshot JSON NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_anomaly_reclassification_receipt_identity (receipt_identity),
    UNIQUE KEY uq_anomaly_reclassification_receipt_disposition (disposition_id),
    UNIQUE KEY uq_anomaly_reclassification_receipt_workflow_event (workflow_event_id),
    INDEX idx_anomaly_reclassification_receipt_state (
        before_state_fingerprint,
        id
    ),
    CONSTRAINT fk_anomaly_reclassification_receipt_disposition
        FOREIGN KEY (disposition_id)
        REFERENCES anomaly_reclassification_dispositions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_reclassification_receipt_workflow_event
        FOREIGN KEY (workflow_event_id)
        REFERENCES anomaly_workflow_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_anomaly_reclassification_receipt_fingerprints
        CHECK (
            before_state_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND after_state_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_anomaly_reclassification_receipt_versions
        CHECK (after_workflow_version = before_workflow_version + 1),
    CONSTRAINT chk_anomaly_reclassification_receipt_snapshot
        CHECK (JSON_TYPE(result_snapshot) = 'OBJECT'),
    CONSTRAINT chk_anomaly_reclassification_receipt_text
        CHECK (
            CHAR_LENGTH(TRIM(receipt_identity)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_reclassification_batch_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_receipt_identity VARCHAR(191) NOT NULL,
    operation_identity VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    eligible_codes JSON NOT NULL,
    eligible_codes_fingerprint CHAR(64) NOT NULL,
    cursor_definition_code VARCHAR(191) NOT NULL DEFAULT '',
    cursor_source_identity VARCHAR(191) NOT NULL DEFAULT '',
    next_cursor_definition_code VARCHAR(191) NULL,
    next_cursor_source_identity VARCHAR(191) NULL,
    batch_size TINYINT UNSIGNED NOT NULL,
    scanned_count INT UNSIGNED NOT NULL,
    applied_count INT UNSIGNED NOT NULL,
    blocked_count INT UNSIGNED NOT NULL,
    before_fingerprints JSON NOT NULL,
    after_fingerprints JSON NOT NULL,
    blocked_items JSON NOT NULL,
    status ENUM('in_progress', 'blocked', 'completed') NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_anomaly_reclassification_batch_receipt_identity (
        batch_receipt_identity
    ),
    UNIQUE KEY uq_anomaly_reclassification_batch_operation_cursor (
        operation_identity,
        cursor_definition_code,
        cursor_source_identity
    ),
    UNIQUE KEY uq_anomaly_reclassification_batch_idempotency (idempotency_key),
    INDEX idx_anomaly_reclassification_batch_status (
        eligible_codes_fingerprint,
        status,
        id
    ),
    CONSTRAINT chk_anomaly_reclassification_batch_size
        CHECK (batch_size BETWEEN 1 AND 100),
    CONSTRAINT chk_anomaly_reclassification_batch_counts
        CHECK (
            scanned_count <= batch_size
            AND applied_count + blocked_count = scanned_count
        ),
    CONSTRAINT chk_anomaly_reclassification_batch_fingerprints
        CHECK (
            JSON_TYPE(eligible_codes) = 'ARRAY'
            AND JSON_LENGTH(eligible_codes) > 0
            AND eligible_codes_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND JSON_TYPE(before_fingerprints) = 'ARRAY'
            AND JSON_TYPE(after_fingerprints) = 'ARRAY'
            AND JSON_TYPE(blocked_items) = 'ARRAY'
        ),
    CONSTRAINT chk_anomaly_reclassification_batch_status
        CHECK (
            (status = 'completed' AND next_cursor_definition_code IS NULL
                AND next_cursor_source_identity IS NULL AND blocked_count = 0)
            OR (status = 'in_progress' AND next_cursor_definition_code IS NOT NULL
                AND next_cursor_source_identity IS NOT NULL AND blocked_count = 0)
            OR (status = 'blocked' AND blocked_count > 0)
        ),
    CONSTRAINT chk_anomaly_reclassification_batch_cursor_pairs
        CHECK (
            ((
                cursor_definition_code = ''
                AND cursor_source_identity = ''
            )
            OR (
                CHAR_LENGTH(TRIM(cursor_definition_code)) > 0
                AND CHAR_LENGTH(TRIM(cursor_source_identity)) > 0
            ))
        AND (
            (
                next_cursor_definition_code IS NULL
                AND next_cursor_source_identity IS NULL
            )
            OR (
                CHAR_LENGTH(TRIM(next_cursor_definition_code)) > 0
                AND CHAR_LENGTH(TRIM(next_cursor_source_identity)) > 0
            )
        )),
    CONSTRAINT chk_anomaly_reclassification_batch_text
        CHECK (
            CHAR_LENGTH(TRIM(batch_receipt_identity)) > 0
            AND CHAR_LENGTH(TRIM(operation_identity)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
            AND request_fingerprint REGEXP '^[0-9a-f]{64}$'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_anomaly_reclassification_dispositions_before_update;
CREATE TRIGGER trg_anomaly_reclassification_dispositions_before_update
BEFORE UPDATE ON anomaly_reclassification_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_reclassification_dispositions records cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_reclassification_dispositions_before_delete;
CREATE TRIGGER trg_anomaly_reclassification_dispositions_before_delete
BEFORE DELETE ON anomaly_reclassification_dispositions
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_reclassification_dispositions records cannot be deleted';

DROP TRIGGER IF EXISTS trg_anomaly_reclassification_receipts_before_update;
CREATE TRIGGER trg_anomaly_reclassification_receipts_before_update
BEFORE UPDATE ON anomaly_reclassification_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_reclassification_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_reclassification_receipts_before_delete;
CREATE TRIGGER trg_anomaly_reclassification_receipts_before_delete
BEFORE DELETE ON anomaly_reclassification_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_reclassification_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_anomaly_reclassification_batch_receipts_before_update;
CREATE TRIGGER trg_anomaly_reclassification_batch_receipts_before_update
BEFORE UPDATE ON anomaly_reclassification_batch_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_reclassification_batch_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_reclassification_batch_receipts_before_delete;
CREATE TRIGGER trg_anomaly_reclassification_batch_receipts_before_delete
BEFORE DELETE ON anomaly_reclassification_batch_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_reclassification_batch_receipts records cannot be deleted';

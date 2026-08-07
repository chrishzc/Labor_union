-- Additive Anomalies registry projection, immutable workflow, and checkpoints.

CREATE TABLE IF NOT EXISTS anomaly_current_alerts (
    fingerprint CHAR(64) PRIMARY KEY,
    definition_code VARCHAR(191) NOT NULL,
    definition_version INT UNSIGNED NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    predicate_active TINYINT(1) NOT NULL,
    workflow_status ENUM('open', 'claimed', 'resolved') NOT NULL,
    workflow_version BIGINT UNSIGNED NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    claimed_by VARCHAR(100) NULL,
    claimed_at DATETIME NULL,
    resolved_by VARCHAR(100) NULL,
    resolved_at DATETIME NULL,
    display_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_anomaly_current_source (
        definition_code,
        source_identity
    ),
    INDEX idx_anomaly_current_workflow (
        predicate_active,
        workflow_status,
        definition_code
    ),
    CONSTRAINT chk_anomaly_current_fingerprint
        CHECK (fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_anomaly_current_display
        CHECK (JSON_TYPE(display_snapshot) = 'OBJECT'),
    CONSTRAINT chk_anomaly_current_workflow
        CHECK (
            (
                workflow_status = 'open'
                AND claimed_by IS NULL
                AND claimed_at IS NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
            )
            OR (
                workflow_status = 'claimed'
                AND CHAR_LENGTH(TRIM(claimed_by)) > 0
                AND claimed_at IS NOT NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
            )
            OR (
                workflow_status = 'resolved'
                AND CHAR_LENGTH(TRIM(resolved_by)) > 0
                AND resolved_at IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_workflow_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_fingerprint CHAR(64) NOT NULL,
    action ENUM('claim', 'resolve', 'reopen', 'auto_resolve') NOT NULL,
    expected_workflow_version BIGINT UNSIGNED NOT NULL,
    resulting_workflow_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_anomaly_workflow_event_idempotency (idempotency_key),
    INDEX idx_anomaly_workflow_event_alert (
        alert_fingerprint,
        resulting_workflow_version
    ),
    CONSTRAINT fk_anomaly_workflow_event_alert
        FOREIGN KEY (alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_anomaly_workflow_event_version
        CHECK (
            resulting_workflow_version = expected_workflow_version + 1
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_anomaly_occurrences (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    occurrence_fingerprint CHAR(64) NOT NULL,
    definition_code VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NULL,
    finance_import_batch_id BIGINT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    bounded_snapshot JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_finance_anomaly_occurrence_fingerprint (
        occurrence_fingerprint
    ),
    UNIQUE KEY uq_finance_anomaly_occurrence_source (
        definition_code,
        source_event_identity
    ),
    CONSTRAINT fk_finance_anomaly_occurrence_row
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_anomaly_occurrence_batch
        FOREIGN KEY (finance_import_batch_id) REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_anomaly_occurrence_fingerprint
        CHECK (occurrence_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_finance_anomaly_occurrence_snapshot
        CHECK (JSON_TYPE(bounded_snapshot) = 'OBJECT'),
    CONSTRAINT chk_finance_anomaly_occurrence_source
        CHECK (
            (finance_import_row_id IS NOT NULL)
            <> (finance_import_batch_id IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_consumer_checkpoints (
    consumer_identity VARCHAR(191) NOT NULL,
    partition_identity VARCHAR(191) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    processed_at DATETIME NOT NULL,
    PRIMARY KEY (consumer_identity, partition_identity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_anomaly_workflow_events_before_update;
CREATE TRIGGER trg_anomaly_workflow_events_before_update
BEFORE UPDATE ON anomaly_workflow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_workflow_events_before_delete;
CREATE TRIGGER trg_anomaly_workflow_events_before_delete
BEFORE DELETE ON anomaly_workflow_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_finance_anomaly_occurrences_before_update;
CREATE TRIGGER trg_finance_anomaly_occurrences_before_update
BEFORE UPDATE ON finance_anomaly_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be updated';

DROP TRIGGER IF EXISTS trg_finance_anomaly_occurrences_before_delete;
CREATE TRIGGER trg_finance_anomaly_occurrences_before_delete
BEFORE DELETE ON finance_anomaly_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be deleted';

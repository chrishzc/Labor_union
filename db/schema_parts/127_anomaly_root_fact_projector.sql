-- Additive root-fact projector receipts and recovery snapshots.

CREATE TABLE IF NOT EXISTS anomaly_root_fact_projection_receipts (
    source_event_identity VARCHAR(191) PRIMARY KEY,
    event_payload_fingerprint CHAR(64) NOT NULL,
    alert_fingerprint CHAR(64) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    predicate_active TINYINT(1) NOT NULL,
    workflow_version BIGINT UNSIGNED NULL,
    occurrence_recorded TINYINT(1) NOT NULL,
    processed_at DATETIME NOT NULL,
    CONSTRAINT chk_anomaly_root_receipt_event_fingerprint
        CHECK (event_payload_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_anomaly_root_receipt_alert_fingerprint
        CHECK (alert_fingerprint REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anomaly_root_fact_snapshots (
    alert_fingerprint CHAR(64) PRIMARY KEY,
    source_event_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    source_occurred_at DATETIME NOT NULL,
    root_condition_active TINYINT(1) NOT NULL,
    integrity_blocker_active TINYINT(1) NOT NULL,
    amount_delta_ntd BIGINT NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    finance_import_batch_id BIGINT NOT NULL,
    affected_order_identities JSON NOT NULL,
    affected_obligation_identities JSON NOT NULL,
    domain_blockers JSON NOT NULL,
    reason_codes JSON NOT NULL,
    projection_freshness ENUM('current', 'stale') NOT NULL DEFAULT 'current',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_anomaly_root_snapshot_alert
        FOREIGN KEY (alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_root_snapshot_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_root_snapshot_batch
        FOREIGN KEY (finance_import_batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_anomaly_root_snapshot_orders
        CHECK (JSON_TYPE(affected_order_identities) = 'ARRAY'),
    CONSTRAINT chk_anomaly_root_snapshot_obligations
        CHECK (JSON_TYPE(affected_obligation_identities) = 'ARRAY'),
    CONSTRAINT chk_anomaly_root_snapshot_blockers
        CHECK (JSON_TYPE(domain_blockers) = 'ARRAY'),
    CONSTRAINT chk_anomaly_root_snapshot_reasons
        CHECK (JSON_TYPE(reason_codes) = 'ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_anomaly_root_receipts_before_update;
CREATE TRIGGER trg_anomaly_root_receipts_before_update
BEFORE UPDATE ON anomaly_root_fact_projection_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly root fact projection receipts cannot be updated';

DROP TRIGGER IF EXISTS trg_anomaly_root_receipts_before_delete;
CREATE TRIGGER trg_anomaly_root_receipts_before_delete
BEFORE DELETE ON anomaly_root_fact_projection_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly root fact projection receipts cannot be deleted';

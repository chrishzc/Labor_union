-- 財務邊界警示的目前人工處理狀態。
-- 本表只保存例外案件與稽核快照，不建立或修改任何正式交易、分配或淨額。
CREATE TABLE IF NOT EXISTS finance_alerts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_key VARCHAR(191) NOT NULL,
    alert_code VARCHAR(100) NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NULL,
    finance_import_batch_id BIGINT NULL,
    reason TEXT NOT NULL,
    expected_amount DECIMAL(18, 2) NULL,
    actual_amount DECIMAL(18, 2) NULL,
    difference_amount DECIMAL(18, 2) NULL,
    candidate_snapshot JSON NOT NULL,
    status ENUM('open', 'claimed', 'resolved') NOT NULL DEFAULT 'open',
    claimed_by VARCHAR(191) NULL,
    claimed_at DATETIME NULL,
    resolved_by VARCHAR(191) NULL,
    resolved_at DATETIME NULL,
    resolution_reason TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_alert_key (alert_key),
    INDEX idx_finance_alert_status (status, created_at),
    INDEX idx_finance_alert_source (
        source_domain,
        source_type,
        source_id
    ),
    INDEX idx_finance_alert_import_row (finance_import_row_id),
    INDEX idx_finance_alert_import_batch (finance_import_batch_id),

    CONSTRAINT fk_finance_alert_import_row
        FOREIGN KEY (finance_import_row_id)
        REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_finance_alert_import_batch
        FOREIGN KEY (finance_import_batch_id)
        REFERENCES finance_import_batches(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_finance_alert_expected_amount
        CHECK (expected_amount IS NULL OR expected_amount >= 0),
    CONSTRAINT chk_finance_alert_actual_amount
        CHECK (actual_amount IS NULL OR actual_amount >= 0),
    CONSTRAINT chk_finance_alert_workflow
        CHECK (
            (
                status = 'open'
                AND claimed_by IS NULL
                AND claimed_at IS NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
                AND resolution_reason IS NULL
            )
            OR
            (
                status = 'claimed'
                AND claimed_by IS NOT NULL
                AND claimed_at IS NOT NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
                AND resolution_reason IS NULL
            )
            OR
            (
                status = 'resolved'
                AND (
                    (claimed_by IS NULL AND claimed_at IS NULL)
                    OR
                    (claimed_by IS NOT NULL AND claimed_at IS NOT NULL)
                )
                AND resolved_by IS NOT NULL
                AND resolved_at IS NOT NULL
                AND resolution_reason IS NOT NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 警示的 append-only 稽核歷程。event_key 由服務依事件來源建立，
-- 唯一鍵使完全相同的匯入重跑或服務重試不會新增第二筆事件。
CREATE TABLE IF NOT EXISTS finance_alert_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_id BIGINT NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(191) NOT NULL,
    actor VARCHAR(191) NULL,
    reason TEXT NULL,
    event_snapshot JSON NOT NULL,
    occurred_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_finance_alert_event_key (event_key),
    INDEX idx_finance_alert_event_history (alert_id, occurred_at, id),
    INDEX idx_finance_alert_event_source (
        source_domain,
        source_type,
        source_id
    ),

    CONSTRAINT fk_finance_alert_event_alert
        FOREIGN KEY (alert_id)
        REFERENCES finance_alerts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

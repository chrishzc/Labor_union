-- File: 1001_line_rich_menu_publication_step_saga.sql
-- Description: Rich Menu 分步確認、provider 嘗試結果與 cleanup anomaly 的不可變保存契約。

-- Option B is additive. The legacy step-receipt table is intentionally retained
-- unchanged; this part has no data copy, seed, backfill, ALTER, or DROP.
CREATE TABLE IF NOT EXISTS line_rich_menu_publication_step_acknowledgements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    step_name ENUM('create','upload','link','switch','cleanup') NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    provider_menu_id VARCHAR(191) NOT NULL,
    acknowledged_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_step_ack (publication_id, step_name),
    UNIQUE KEY uq_line_rich_menu_step_ack_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_step_ack_publication (publication_id, id),
    CONSTRAINT fk_line_rich_menu_step_ack_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_rich_menu_step_ack_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_rich_menu_step_ack_provider_id
        CHECK (CHAR_LENGTH(TRIM(provider_menu_id)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_step_attempt_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    step_name ENUM('create','upload','link','switch','cleanup') NOT NULL,
    attempt_number INT UNSIGNED NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    outcome ENUM(
        'success','rate_limited','rejected','unavailable','timeout','lost_ack'
    ) NOT NULL,
    provider_menu_id VARCHAR(191) NULL,
    error_code VARCHAR(191) NULL,
    attempted_at_utc DATETIME(6) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_step_attempt (
        publication_id, step_name, attempt_number
    ),
    UNIQUE KEY uq_line_rich_menu_step_attempt_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_step_attempt_publication (
        publication_id, step_name, attempt_number
    ),
    CONSTRAINT fk_line_rich_menu_step_attempt_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_rich_menu_step_attempt_number
        CHECK (attempt_number > 0),
    CONSTRAINT chk_line_rich_menu_step_attempt_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_rich_menu_step_attempt_outcome
        CHECK (
            (outcome = 'success'
                AND provider_menu_id IS NOT NULL
                AND CHAR_LENGTH(TRIM(provider_menu_id)) > 0
                AND error_code IS NULL)
            OR
            (outcome <> 'success'
                AND provider_menu_id IS NULL
                AND error_code IS NOT NULL
                AND CHAR_LENGTH(TRIM(error_code)) > 0)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_cleanup_anomalies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    error_code VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_cleanup_anomaly_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_cleanup_anomaly_publication (publication_id, id),
    CONSTRAINT fk_line_rich_menu_cleanup_anomaly_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_rich_menu_cleanup_anomaly_fingerprint
        CHECK (request_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_rich_menu_cleanup_anomaly_error
        CHECK (CHAR_LENGTH(TRIM(error_code)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_ack_before_update;
CREATE TRIGGER trg_line_rich_menu_step_ack_before_update
BEFORE UPDATE ON line_rich_menu_publication_step_acknowledgements
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_acknowledgements records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_ack_before_delete;
CREATE TRIGGER trg_line_rich_menu_step_ack_before_delete
BEFORE DELETE ON line_rich_menu_publication_step_acknowledgements
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_acknowledgements records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_attempt_before_update;
CREATE TRIGGER trg_line_rich_menu_step_attempt_before_update
BEFORE UPDATE ON line_rich_menu_publication_step_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_attempt_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_attempt_before_delete;
CREATE TRIGGER trg_line_rich_menu_step_attempt_before_delete
BEFORE DELETE ON line_rich_menu_publication_step_attempt_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_attempt_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_line_rich_menu_cleanup_anomaly_before_update;
CREATE TRIGGER trg_line_rich_menu_cleanup_anomaly_before_update
BEFORE UPDATE ON line_rich_menu_publication_cleanup_anomalies
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_cleanup_anomalies records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_cleanup_anomaly_before_delete;
CREATE TRIGGER trg_line_rich_menu_cleanup_anomaly_before_delete
BEFORE DELETE ON line_rich_menu_publication_cleanup_anomalies
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_cleanup_anomalies records cannot be deleted';

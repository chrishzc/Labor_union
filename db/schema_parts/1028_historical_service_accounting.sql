-- Historical lifecycle branch and count-based service accounting roots.
-- Additive/shape-widening only; no existing row is rewritten or backfilled.

ALTER TABLE orders
    MODIFY COLUMN `status` ENUM(
        '待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消',
        '歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成'
    ) NOT NULL DEFAULT '洽談中';

ALTER TABLE order_lifecycle_state_events
    DROP CHECK chk_order_lifecycle_state_event_before_status,
    DROP CHECK chk_order_lifecycle_state_event_after_status,
    ADD CONSTRAINT chk_order_lifecycle_state_event_before_status CHECK (
        before_status IN (
            '待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消',
            '歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成'
        )
    ),
    ADD CONSTRAINT chk_order_lifecycle_state_event_after_status CHECK (
        after_status IN (
            '待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消',
            '歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成'
        )
    );

CREATE TABLE IF NOT EXISTS historical_service_day_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_identity VARCHAR(191) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    historical_adoption_receipt_id BIGINT UNSIGNED NOT NULL,
    expected_day_revision BIGINT UNSIGNED NOT NULL,
    resulting_day_revision BIGINT UNSIGNED NOT NULL,
    total_actual_service_days INT UNSIGNED NOT NULL,
    total_actual_service_hours DECIMAL(12,2) NOT NULL,
    historical_floor_fee_ntd BIGINT NOT NULL,
    client_obligation_amount_ntd BIGINT NOT NULL,
    staff_obligation_amount_ntd BIGINT NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor_id VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    result_snapshot JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_service_day_event_identity (event_identity),
    UNIQUE KEY uq_historical_service_day_idempotency (idempotency_key),
    INDEX idx_historical_service_day_case_revision (case_no,resulting_day_revision),
    CONSTRAINT fk_historical_service_day_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_service_day_adoption FOREIGN KEY (historical_adoption_receipt_id)
        REFERENCES historical_order_adoption_receipts(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_service_day_revision CHECK (resulting_day_revision=expected_day_revision+1),
    CONSTRAINT chk_historical_service_day_values CHECK (
        total_actual_service_days>0 AND total_actual_service_hours>0
        AND historical_floor_fee_ntd>=0 AND client_obligation_amount_ntd>=0
        AND staff_obligation_amount_ntd>0
    ),
    CONSTRAINT chk_historical_service_day_fingerprints CHECK (
        preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_historical_service_day_snapshot CHECK (JSON_TYPE(result_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_service_day_items (
    event_id BIGINT UNSIGNED NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    item_ordinal INT UNSIGNED NOT NULL,
    actual_service_days INT UNSIGNED NOT NULL,
    actual_service_hours DECIMAL(12,2) NOT NULL,
    floor_fee_allocated_ntd BIGINT NOT NULL,
    staff_obligation_amount_ntd BIGINT NOT NULL,
    payroll_policy_version VARCHAR(100) NOT NULL,
    payroll_policy_kind ENUM('citizen','subsidized_citizen','non_citizen') NOT NULL,
    hourly_rate_ntd BIGINT NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id,assignment_id),
    UNIQUE KEY uq_historical_service_day_item_ordinal (event_id,item_ordinal),
    CONSTRAINT fk_historical_service_day_item_event FOREIGN KEY (event_id)
        REFERENCES historical_service_day_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_service_day_item_assignment FOREIGN KEY (assignment_id)
        REFERENCES case_staff_assignments(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_service_day_item_staff FOREIGN KEY (staff_id)
        REFERENCES staff(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_service_day_item_policy FOREIGN KEY (payroll_policy_version,payroll_policy_kind)
        REFERENCES payroll_rate_policies(policy_version,policy_kind) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_service_day_item_values CHECK (
        item_ordinal>0 AND actual_service_days>0 AND actual_service_hours>0
        AND floor_fee_allocated_ntd>=0 AND staff_obligation_amount_ntd>0 AND hourly_rate_ntd>0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_service_day_projections (
    case_no VARCHAR(50) PRIMARY KEY,
    current_event_id BIGINT UNSIGNED NOT NULL,
    historical_adoption_receipt_id BIGINT UNSIGNED NOT NULL,
    day_revision BIGINT UNSIGNED NOT NULL,
    total_actual_service_days INT UNSIGNED NOT NULL,
    total_actual_service_hours DECIMAL(12,2) NOT NULL,
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_service_day_projection_event (current_event_id),
    CONSTRAINT fk_historical_service_day_projection_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_service_day_projection_event FOREIGN KEY (current_event_id)
        REFERENCES historical_service_day_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_historical_service_day_projection_adoption FOREIGN KEY (historical_adoption_receipt_id)
        REFERENCES historical_order_adoption_receipts(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_service_day_projection_values CHECK (
        day_revision>0 AND total_actual_service_days>0 AND total_actual_service_hours>0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_service_accounting_outbox (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED NOT NULL,
    intent_key VARCHAR(191) NOT NULL,
    intent_type ENUM('historical_service_accounting_applied') NOT NULL,
    bounded_snapshot JSON NOT NULL,
    published_at DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_historical_service_accounting_outbox_intent (intent_key),
    INDEX idx_historical_service_accounting_outbox_pending (published_at,id),
    CONSTRAINT fk_historical_service_accounting_outbox_event FOREIGN KEY (event_id)
        REFERENCES historical_service_day_events(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_historical_service_accounting_outbox_snapshot CHECK (JSON_TYPE(bounded_snapshot)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_historical_service_day_events_before_update;
CREATE TRIGGER trg_historical_service_day_events_before_update BEFORE UPDATE ON historical_service_day_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_events records cannot be updated';
DROP TRIGGER IF EXISTS trg_historical_service_day_events_before_delete;
CREATE TRIGGER trg_historical_service_day_events_before_delete BEFORE DELETE ON historical_service_day_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_events records cannot be deleted';
DROP TRIGGER IF EXISTS trg_historical_service_day_items_before_update;
CREATE TRIGGER trg_historical_service_day_items_before_update BEFORE UPDATE ON historical_service_day_items FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_items records cannot be updated';
DROP TRIGGER IF EXISTS trg_historical_service_day_items_before_delete;
CREATE TRIGGER trg_historical_service_day_items_before_delete BEFORE DELETE ON historical_service_day_items FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_items records cannot be deleted';

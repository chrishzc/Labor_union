ALTER TABLE confirmed_service_date_days
    ADD COLUMN staff_id INT NULL,
    ADD COLUMN service_hours_override TINYINT UNSIGNED NULL,
    ADD CONSTRAINT fk_confirmed_service_day_staff FOREIGN KEY (staff_id) REFERENCES staff(id),
    ADD CONSTRAINT chk_confirmed_service_day_hours
        CHECK (service_hours_override IS NULL OR (service_hours_override IN (4,8) AND staff_id IS NOT NULL));

ALTER TABLE staff_schedule
    ADD COLUMN service_hours_override TINYINT UNSIGNED NULL,
    ADD CONSTRAINT chk_staff_schedule_service_day_hours
        CHECK (service_hours_override IS NULL OR service_hours_override IN (4,8)),
    DROP INDEX uq_staff_schedule_generation_owner,
    ADD UNIQUE KEY uq_staff_schedule_effective_generation_day (generation_id,work_date,effective_marker);

CREATE TABLE IF NOT EXISTS service_date_adjustment_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    command_fingerprint CHAR(64) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reverse_receipt_id BIGINT UNSIGNED NULL,
    result_snapshot JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_service_date_adjustment_receipt_key (idempotency_key),
    KEY idx_service_date_adjustment_case (case_no,id),
    CONSTRAINT fk_service_date_adjustment_case FOREIGN KEY (case_no) REFERENCES orders(case_no),
    CONSTRAINT fk_service_date_adjustment_reverse FOREIGN KEY (reverse_receipt_id)
        REFERENCES service_date_adjustment_receipts(id),
    CONSTRAINT chk_service_date_adjustment_snapshot CHECK (JSON_TYPE(result_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

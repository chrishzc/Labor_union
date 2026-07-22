-- 保存已成功套用的訂單服務變更與正式月嫂指派配置；不可作為薪資或時數覆寫來源。
CREATE TABLE IF NOT EXISTS order_assignment_change_audits (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    order_before_snapshot JSON NOT NULL,
    order_after_snapshot JSON NOT NULL,
    assignment_plan_snapshot JSON NOT NULL,
    applied_by VARCHAR(100) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order_assignment_change_audit_case_time (case_no, applied_at),
    CONSTRAINT chk_order_assignment_change_audit_applied_by
        CHECK (CHAR_LENGTH(TRIM(applied_by)) > 0),
    CONSTRAINT fk_order_assignment_change_audit_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

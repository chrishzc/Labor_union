-- 服務人員月結明細：凍結逐案件、逐服務指派的應付構成。
-- 實際銀行轉帳另由月結付款分配記錄，不得反寫本表的應付快照。
CREATE TABLE IF NOT EXISTS staff_monthly_settlement_details (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    settlement_id BIGINT NOT NULL,
    staff_payment_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    service_salary DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '一般服務薪資快照',
    legacy_subsidy_payable DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '舊制補助應付構成快照',
    floor_fee_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '樓層費快照',
    adjustment_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '可正可負的人工調整快照',
    payable_amount DECIMAL(12, 2) NOT NULL COMMENT '應付構成合計快照',
    legacy_subsidy_status ENUM(
        'not_applicable',
        'confirmed',
        'review_required'
    ) NOT NULL DEFAULT 'not_applicable',
    review_required BOOLEAN NOT NULL DEFAULT FALSE,
    review_note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_monthly_settlement_detail_payment (settlement_id, staff_payment_id),
    INDEX idx_staff_monthly_settlement_detail_staff (staff_id, settlement_id),
    INDEX idx_staff_monthly_settlement_detail_case (case_no, assignment_id),
    CONSTRAINT fk_staff_monthly_settlement_detail_settlement
        FOREIGN KEY (settlement_id) REFERENCES staff_monthly_settlements(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_payment
        FOREIGN KEY (staff_payment_id) REFERENCES staff_payments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_monthly_settlement_detail_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_monthly_settlement_detail_components
        CHECK (
            service_salary >= 0
            AND legacy_subsidy_payable >= 0
            AND floor_fee_amount >= 0
            AND payable_amount >= 0
            AND payable_amount = (
                service_salary
                + legacy_subsidy_payable
                + floor_fee_amount
                + adjustment_amount
            )
        ),
    CONSTRAINT chk_staff_monthly_settlement_detail_review_state
        CHECK (
            (
                legacy_subsidy_status = 'review_required'
                AND review_required = TRUE
            )
            OR (
                legacy_subsidy_status <> 'review_required'
                AND review_required = FALSE
            )
        ),
    CONSTRAINT chk_staff_monthly_settlement_detail_legacy_subsidy
        CHECK (
            legacy_subsidy_payable = 0
            OR legacy_subsidy_status IN ('confirmed', 'review_required')
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 服務人員月結摘要：每位服務人員、每個薪資歸屬月、每個修訂版一筆。
-- settlement_month 是薪資歸屬月份，不得由銀行交易日期回寫。
CREATE TABLE IF NOT EXISTS staff_monthly_settlements (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    settlement_month DATE NOT NULL COMMENT '薪資歸屬月份；固定使用該月首日',
    revision INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '同一服務人員同月的月結修訂版，從 1 起',
    total_payable DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '月結明細應付快照合計',
    total_paid DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '成功轉帳分配的淨額投影，不得人工覆寫',
    status ENUM(
        'draft',
        'finalized',
        'partially_paid',
        'paid',
        'cancelled',
        'review_required'
    ) NOT NULL DEFAULT 'draft',
    finalized_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_monthly_settlement_revision (staff_id, settlement_month, revision),
    INDEX idx_staff_monthly_settlement_status (settlement_month, status),
    CONSTRAINT fk_staff_monthly_settlement_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_staff_monthly_settlement_month_start
        CHECK (DAY(settlement_month) = 1),
    CONSTRAINT chk_staff_monthly_settlement_revision
        CHECK (revision >= 1),
    CONSTRAINT chk_staff_monthly_settlement_totals
        CHECK (
            total_payable >= 0
            AND total_paid >= 0
            AND total_paid <= total_payable
        ),
    CONSTRAINT chk_staff_monthly_settlement_finalized_at
        CHECK (
            status <> 'finalized'
            OR finalized_at IS NOT NULL
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

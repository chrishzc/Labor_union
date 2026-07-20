-- 正式季度政府補助申請批次；revision 由建立流程明確提供。
CREATE TABLE IF NOT EXISTS subsidy_claim_batches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_year SMALLINT UNSIGNED NOT NULL,
    quarter TINYINT UNSIGNED NOT NULL,
    revision INT UNSIGNED NOT NULL,
    status ENUM(
        'draft',
        'submitted',
        'approved',
        'partially_paid',
        'paid'
    ) NOT NULL DEFAULT 'draft',
    requested_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '送件時凍結的批次申請總額',
    approved_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '政府核准總額，不覆寫申請總額',
    paid_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '銀行撥款分配總額，不覆寫申請或核准總額',
    submitted_at DATETIME NULL,
    approved_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_subsidy_claim_batch_revision (application_year, quarter, revision),
    INDEX idx_subsidy_claim_batch_status (application_year, quarter, status),
    CONSTRAINT chk_subsidy_claim_batch_year CHECK (application_year >= 1),
    CONSTRAINT chk_subsidy_claim_batch_quarter CHECK (quarter BETWEEN 1 AND 4),
    CONSTRAINT chk_subsidy_claim_batch_revision CHECK (revision >= 1),
    CONSTRAINT chk_subsidy_claim_batch_amounts CHECK (
        requested_amount >= 0
        AND approved_amount >= 0
        AND paid_amount >= 0
    ),
    CONSTRAINT chk_subsidy_claim_batch_state_times CHECK (
        (status = 'draft' AND submitted_at IS NULL AND approved_at IS NULL)
        OR (status = 'submitted' AND submitted_at IS NOT NULL AND approved_at IS NULL)
        OR (status IN ('approved', 'partially_paid', 'paid')
            AND submitted_at IS NOT NULL
            AND approved_at IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 批次內逐服務指派的申請、核准與已撥快照。
CREATE TABLE IF NOT EXISTS subsidy_claim_batch_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    assignment_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    claimed_hours DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    unit_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    requested_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00 COMMENT '建立批次時凍結，不由核准或撥款流程覆寫',
    approved_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    paid_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_subsidy_claim_batch_assignment (batch_id, assignment_id),
    INDEX idx_subsidy_claim_batch_item_case (case_no),
    INDEX idx_subsidy_claim_batch_item_staff (staff_id),
    CONSTRAINT fk_subsidy_claim_batch_item_batch
        FOREIGN KEY (batch_id) REFERENCES subsidy_claim_batches(id) ON DELETE RESTRICT,
    CONSTRAINT fk_subsidy_claim_batch_item_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_subsidy_claim_batch_item_assignment
        FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments(id) ON DELETE RESTRICT,
    CONSTRAINT fk_subsidy_claim_batch_item_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT chk_subsidy_claim_batch_item_values CHECK (
        claimed_hours >= 0
        AND unit_price >= 0
        AND requested_amount >= 0
        AND approved_amount >= 0
        AND paid_amount >= 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

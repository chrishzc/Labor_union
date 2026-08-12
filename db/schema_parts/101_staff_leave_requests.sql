CREATE TABLE IF NOT EXISTS staff_leave_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL COMMENT '提出請假的月嫂',
    line_user_id VARCHAR(100) NOT NULL COMMENT '提出申請的 LINE 用戶',
    leave_start_date DATE NOT NULL COMMENT '請假開始日期',
    leave_end_date DATE NOT NULL COMMENT '請假結束日期',
    leave_reason TEXT NULL COMMENT '請假原因',
    substitute_found BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否已找到代班人員',
    substitute_name VARCHAR(100) NULL COMMENT '代班人員姓名',
    substitute_phone VARCHAR(30) NULL COMMENT '代班人員電話',
    substitute_note TEXT NULL COMMENT '代班補充資訊',
    status ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending',
    reviewed_by_admin_user_id BIGINT NULL COMMENT '審核工會人員',
    reviewed_at DATETIME NULL COMMENT '審核時間',
    review_note TEXT NULL COMMENT '審核備註',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_staff_leave_staff_status (staff_id, status, leave_start_date),
    INDEX idx_staff_leave_line_user (line_user_id, created_at),
    CONSTRAINT fk_staff_leave_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE RESTRICT,
    CONSTRAINT fk_staff_leave_reviewer
        FOREIGN KEY (reviewed_by_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

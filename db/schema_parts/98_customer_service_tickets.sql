CREATE TABLE IF NOT EXISTS customer_service_tickets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL COMMENT '提出需求的 LINE 用戶',
    client_id INT NULL COMMENT '已綁定客戶時連結 clients.id',
    case_no VARCHAR(50) NULL COMMENT '已綁定案件時連結 orders.case_no',
    category ENUM(
        'service_flow',
        'payment_subsidy',
        'service_progress',
        'profile_update',
        'contact_union',
        'other'
    ) NOT NULL,
    message TEXT NOT NULL COMMENT '用戶原始問題或系統分類內容',
    status ENUM('waiting','handling','resolved') NOT NULL DEFAULT 'waiting',
    assigned_to_admin_user_id BIGINT NULL COMMENT '目前處理人員',
    internal_note TEXT NULL COMMENT '工會內部備註',
    last_reply TEXT NULL COMMENT '最近一次回覆客戶內容',
    last_replied_at DATETIME NULL,
    resolved_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_customer_service_status_time (status, created_at),
    INDEX idx_customer_service_line_user (line_user_id, status),
    INDEX idx_customer_service_client (client_id, created_at),
    INDEX idx_customer_service_case_no (case_no),
    CONSTRAINT fk_customer_service_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_assigned_admin
        FOREIGN KEY (assigned_to_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

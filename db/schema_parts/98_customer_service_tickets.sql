CREATE TABLE IF NOT EXISTS customer_service_tickets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL,
    client_id INT NULL,
    case_no VARCHAR(50) NULL,
    category ENUM('service_flow','payment_subsidy','service_progress','profile_update','contact_union','other') NOT NULL,
    status ENUM('waiting','handling','resolved') NOT NULL DEFAULT 'waiting',
    assigned_to_admin_user_id BIGINT NULL,
    internal_note TEXT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    resolved_at_utc DATETIME NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    active_marker TINYINT GENERATED ALWAYS AS (
        CASE WHEN status IN ('waiting','handling') THEN 1 ELSE NULL END
    ) STORED,
    UNIQUE KEY uq_customer_service_active_category (line_user_id, category, active_marker),
    INDEX idx_customer_service_status_time (status, created_at_utc),
    INDEX idx_customer_service_client (client_id, created_at_utc),
    INDEX idx_customer_service_case (case_no, created_at_utc),
    CONSTRAINT fk_customer_service_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_order FOREIGN KEY (case_no)
        REFERENCES orders(case_no) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_customer_service_admin FOREIGN KEY (assigned_to_admin_user_id)
        REFERENCES admin_users(id) ON UPDATE RESTRICT ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_profile_change_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL COMMENT '提出異動申請的 LINE 用戶',
    client_id INT NOT NULL COMMENT '欲異動的客戶資料',
    case_no VARCHAR(50) NULL COMMENT '申請當下的案件編號',
    ticket_id BIGINT NULL COMMENT '關聯客服單',
    status ENUM('pending','approved','partially_approved','rejected','reverted') NOT NULL DEFAULT 'pending',
    requested_changes_json JSON NOT NULL COMMENT '用戶送出的欄位異動內容',
    old_values_json JSON NOT NULL COMMENT '送出當下 DB 原始值快照',
    applied_values_json JSON NULL COMMENT '審核通過後實際套用的新值',
    rejection_reason TEXT NULL,
    reviewed_by_name VARCHAR(100) NULL COMMENT '審核人員姓名快照',
    reviewed_by_admin_user_id BIGINT NULL COMMENT '審核工會人員',
    reviewed_at DATETIME NULL COMMENT '審核時間',
    reverted_by_name VARCHAR(100) NULL COMMENT '回復人員姓名快照',
    reverted_by_admin_user_id BIGINT NULL COMMENT '回復工會人員',
    reverted_at DATETIME NULL COMMENT '回復時間',
    revert_reason TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_client_profile_change_status_time (status, created_at),
    INDEX idx_client_profile_change_line_user (line_user_id, created_at),
    INDEX idx_client_profile_change_client (client_id, created_at),
    INDEX idx_client_profile_change_ticket (ticket_id),
    CONSTRAINT fk_client_profile_change_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    CONSTRAINT fk_client_profile_change_ticket
        FOREIGN KEY (ticket_id) REFERENCES customer_service_tickets(id) ON DELETE SET NULL,
    CONSTRAINT fk_client_profile_change_reviewer
        FOREIGN KEY (reviewed_by_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL,
    CONSTRAINT fk_client_profile_change_reverter
        FOREIGN KEY (reverted_by_admin_user_id) REFERENCES admin_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @profile_change_reviewed_by_name_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_profile_change_requests'
      AND COLUMN_NAME = 'reviewed_by_name'
);
SET @profile_change_reviewed_by_name_sql = IF(
    @profile_change_reviewed_by_name_exists = 0,
    'ALTER TABLE client_profile_change_requests ADD COLUMN reviewed_by_name VARCHAR(100) NULL COMMENT ''審核人員姓名快照'' AFTER rejection_reason',
    'SELECT 1'
);
PREPARE profile_change_reviewed_by_name_stmt FROM @profile_change_reviewed_by_name_sql;
EXECUTE profile_change_reviewed_by_name_stmt;
DEALLOCATE PREPARE profile_change_reviewed_by_name_stmt;

SET @profile_change_reverted_by_name_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_profile_change_requests'
      AND COLUMN_NAME = 'reverted_by_name'
);
SET @profile_change_reverted_by_name_sql = IF(
    @profile_change_reverted_by_name_exists = 0,
    'ALTER TABLE client_profile_change_requests ADD COLUMN reverted_by_name VARCHAR(100) NULL COMMENT ''回復人員姓名快照'' AFTER reviewed_at',
    'SELECT 1'
);
PREPARE profile_change_reverted_by_name_stmt FROM @profile_change_reverted_by_name_sql;
EXECUTE profile_change_reverted_by_name_stmt;
DEALLOCATE PREPARE profile_change_reverted_by_name_stmt;

SET @profile_change_status_type = (
    SELECT COLUMN_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'client_profile_change_requests'
      AND COLUMN_NAME = 'status'
);
SET @profile_change_status_sql = IF(
    @profile_change_status_type NOT LIKE '%partially_approved%',
    'ALTER TABLE client_profile_change_requests MODIFY COLUMN status ENUM(''pending'',''approved'',''partially_approved'',''rejected'',''reverted'') NOT NULL DEFAULT ''pending''',
    'SELECT 1'
);
PREPARE profile_change_status_stmt FROM @profile_change_status_sql;
EXECUTE profile_change_status_stmt;
DEALLOCATE PREPARE profile_change_status_stmt;

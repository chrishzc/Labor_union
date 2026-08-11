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

CREATE TABLE IF NOT EXISTS customer_service_ticket_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticket_id BIGINT NOT NULL,
    event_key VARCHAR(191) NOT NULL,
    event_type ENUM('customer_message','agent_reply','status_changed','internal_note') NOT NULL,
    message_text TEXT NULL,
    actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_customer_service_event_key (event_key),
    INDEX idx_customer_service_ticket_events (ticket_id, id),
    CONSTRAINT fk_customer_service_event_ticket FOREIGN KEY (ticket_id)
        REFERENCES customer_service_tickets(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

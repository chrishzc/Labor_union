CREATE TABLE IF NOT EXISTS provisional_client_registrations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    line_user_id VARCHAR(100) NOT NULL,
    active_line_user_id VARCHAR(100) NULL,
    payload_fingerprint CHAR(64) NOT NULL,
    status ENUM('submitted','case_issued') NOT NULL DEFAULT 'submitted',
    client_id INT NULL,
    beclass_record_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provisional_registration_active_line_user (active_line_user_id),
    INDEX idx_provisional_registration_line_status (line_user_id, status),
    CONSTRAINT chk_provisional_registration_fingerprint CHECK (
        payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT fk_provisional_registration_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_registration_beclass
        FOREIGN KEY (beclass_record_id) REFERENCES beclass_records(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS provisional_registration_conflicts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    registration_id BIGINT NOT NULL,
    proposed_payload_fingerprint CHAR(64) NOT NULL,
    proposed_payload JSON NOT NULL,
    status ENUM('open','resolved') NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provisional_registration_conflict (
        registration_id, proposed_payload_fingerprint
    ),
    INDEX idx_provisional_registration_conflict_status (status, created_at),
    CONSTRAINT chk_provisional_registration_conflict_fingerprint CHECK (
        proposed_payload_fingerprint REGEXP '^[0-9a-f]{64}$'
    ),
    CONSTRAINT fk_provisional_registration_conflict_registration
        FOREIGN KEY (registration_id) REFERENCES provisional_client_registrations(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

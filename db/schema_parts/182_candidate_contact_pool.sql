-- 182. Candidate Contact Pool: negotiation contacts, never formal service segments.
CREATE TABLE IF NOT EXISTS caregiver_candidate_contact_pools (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_candidate_contact_pool_case (case_no),
    CONSTRAINT fk_candidate_contact_pool_case FOREIGN KEY (case_no) REFERENCES orders(case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caregiver_candidate_contact_entries (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pool_id BIGINT UNSIGNED NOT NULL,
    staff_id INT NOT NULL,
    service_start_date DATE NOT NULL,
    service_end_date DATE NOT NULL,
    coverage_fingerprint CHAR(64) NOT NULL,
    status ENUM('active','selected','withdrawn') NOT NULL DEFAULT 'active',
    active_marker TINYINT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_candidate_contact_active_staff (pool_id,staff_id,active_marker),
    CONSTRAINT fk_candidate_contact_entry_pool FOREIGN KEY (pool_id) REFERENCES caregiver_candidate_contact_pools(id),
    CONSTRAINT fk_candidate_contact_entry_staff FOREIGN KEY (staff_id) REFERENCES staff(id),
    CONSTRAINT chk_candidate_contact_dates CHECK (service_start_date<=service_end_date),
    CONSTRAINT chk_candidate_contact_active CHECK (active_marker IS NULL OR active_marker=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caregiver_candidate_contact_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pool_id BIGINT UNSIGNED NOT NULL,
    candidate_id BIGINT UNSIGNED NULL,
    event_type ENUM('candidates_added','info_1_sent','info_2_sent','willingness_changed','candidate_selected','candidate_withdrawn') NOT NULL,
    event_key VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_candidate_contact_event_key (event_key),
    KEY idx_candidate_contact_event_candidate (candidate_id,occurred_at),
    CONSTRAINT fk_candidate_contact_event_pool FOREIGN KEY (pool_id) REFERENCES caregiver_candidate_contact_pools(id),
    CONSTRAINT fk_candidate_contact_event_candidate FOREIGN KEY (candidate_id) REFERENCES caregiver_candidate_contact_entries(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

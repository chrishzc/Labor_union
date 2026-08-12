CREATE TABLE IF NOT EXISTS provisional_registration_case_issue_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    registration_id BIGINT NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    client_id INT NOT NULL,
    beclass_record_id INT NOT NULL,
    case_import_event_id BIGINT NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provisional_case_issue_registration (registration_id),
    UNIQUE KEY uq_provisional_case_issue_case (case_no),
    UNIQUE KEY uq_provisional_case_issue_idempotency (idempotency_key),
    CONSTRAINT fk_provisional_case_issue_registration FOREIGN KEY (registration_id)
        REFERENCES provisional_client_registrations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_case_issue_client FOREIGN KEY (client_id)
        REFERENCES clients(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_case_issue_beclass FOREIGN KEY (beclass_record_id)
        REFERENCES beclass_records(id) ON DELETE RESTRICT,
    CONSTRAINT fk_provisional_case_issue_import_event FOREIGN KEY (case_import_event_id)
        REFERENCES case_import_events(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE case_import_receipts
    ADD COLUMN provisional_registration_id BIGINT NULL,
    ADD COLUMN provisional_case_issue_event_id BIGINT NULL,
    ADD CONSTRAINT fk_case_import_receipt_provisional_registration
        FOREIGN KEY (provisional_registration_id) REFERENCES provisional_client_registrations(id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT fk_case_import_receipt_provisional_issue_event
        FOREIGN KEY (provisional_case_issue_event_id) REFERENCES provisional_registration_case_issue_events(id)
        ON DELETE RESTRICT;

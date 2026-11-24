ALTER TABLE controlled_file_staging_objects
    MODIFY COLUMN purpose ENUM(
        'unsigned_contract', 'final_signed_contract', 'service_date_confirmation',
        'baby_log_photo', 'meal_photo', 'order_notice', 'staff_resume',
        'staff_certificate', 'staff_health_exam', 'client_passbook_cover', 'rich_menu_background', 'staff_profile_photo'
    ) NOT NULL,
    DROP CHECK chk_controlled_file_staging_owner_purpose,
    ADD CONSTRAINT chk_controlled_file_staging_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose IN ('unsigned_contract', 'final_signed_contract'))
        OR (owner_type = 'scheduling' AND purpose IN ('service_date_confirmation', 'baby_log_photo', 'meal_photo'))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN ('staff_resume', 'staff_certificate', 'staff_health_exam', 'staff_profile_photo'))
        OR (owner_type = 'clients' AND purpose = 'client_passbook_cover')
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    );

ALTER TABLE controlled_file_objects
    DROP FOREIGN KEY fk_controlled_file_object_supersedes;

ALTER TABLE controlled_file_objects
    MODIFY COLUMN purpose ENUM(
        'unsigned_contract', 'final_signed_contract', 'service_date_confirmation',
        'baby_log_photo', 'meal_photo', 'order_notice', 'staff_resume',
        'staff_certificate', 'staff_health_exam', 'client_passbook_cover', 'rich_menu_background', 'staff_profile_photo'
    ) NOT NULL,
    DROP CHECK chk_controlled_file_object_owner_purpose,
    ADD CONSTRAINT chk_controlled_file_object_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose IN ('unsigned_contract', 'final_signed_contract'))
        OR (owner_type = 'scheduling' AND purpose IN ('service_date_confirmation', 'baby_log_photo', 'meal_photo'))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN ('staff_resume', 'staff_certificate', 'staff_health_exam', 'staff_profile_photo'))
        OR (owner_type = 'clients' AND purpose = 'client_passbook_cover')
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    );

ALTER TABLE controlled_file_objects
    ADD CONSTRAINT fk_controlled_file_object_supersedes FOREIGN KEY (
        supersedes_object_id, owner_type, subject_reference, object_key,
        purpose, supersedes_version_number
    ) REFERENCES controlled_file_objects (
        id, owner_type, subject_reference, object_key, purpose, version_number
    ) ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS staff_web_template_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    name VARCHAR(100) NOT NULL,
    category ENUM('photo','certificate','other') NOT NULL,
    display_order INT UNSIGNED NOT NULL,
    reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    reminder_months SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    reminder_days SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    updated_by VARCHAR(191) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT chk_staff_web_template_reminder CHECK (category = 'other' OR reminder_enabled = FALSE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_web_entries (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    template_item_id BIGINT UNSIGNED NOT NULL,
    published_version BIGINT UNSIGNED NOT NULL,
    INDEX idx_staff_web_entry_staff (staff_id, template_item_id, id),
    CONSTRAINT fk_staff_web_entry_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_web_entry_template FOREIGN KEY (template_item_id) REFERENCES staff_web_template_items(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_web_publications (
    entry_id BIGINT UNSIGNED NOT NULL,
    version BIGINT UNSIGNED NOT NULL,
    original_file_id VARCHAR(64) NOT NULL,
    crop_file_id VARCHAR(64) NULL,
    expiry_date DATE NULL,
    approved_by VARCHAR(191) NOT NULL,
    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (entry_id, version),
    UNIQUE KEY uq_staff_web_original (original_file_id),
    UNIQUE KEY uq_staff_web_crop (crop_file_id),
    INDEX idx_staff_web_publication_expiry (expiry_date, entry_id, version),
    CONSTRAINT fk_staff_web_publication_entry FOREIGN KEY (entry_id) REFERENCES staff_web_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_web_publication_original FOREIGN KEY (original_file_id)
        REFERENCES controlled_file_objects(opaque_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_web_publication_crop FOREIGN KEY (crop_file_id)
        REFERENCES controlled_file_objects(opaque_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_web_approval_receipts (
    operation_id CHAR(36) NOT NULL PRIMARY KEY,
    staff_id INT NOT NULL,
    publication_results JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_staff_web_receipt_staff FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

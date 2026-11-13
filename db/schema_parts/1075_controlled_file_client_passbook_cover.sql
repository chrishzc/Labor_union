-- Publish the existing controlled-file contract for client passbook covers.
ALTER TABLE controlled_file_staging_objects
    MODIFY COLUMN owner_type ENUM(
        'contract_signing', 'scheduling', 'orders', 'staff', 'clients', 'line_integration'
    ) NOT NULL,
    MODIFY COLUMN purpose ENUM(
        'unsigned_contract', 'final_signed_contract', 'service_date_confirmation',
        'baby_log_photo', 'meal_photo', 'order_notice', 'staff_resume',
        'staff_certificate', 'staff_health_exam', 'client_passbook_cover', 'rich_menu_background'
    ) NOT NULL,
    DROP CHECK chk_controlled_file_staging_owner_purpose,
    ADD CONSTRAINT chk_controlled_file_staging_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose IN ('unsigned_contract', 'final_signed_contract'))
        OR (owner_type = 'scheduling' AND purpose IN ('service_date_confirmation', 'baby_log_photo', 'meal_photo'))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN ('staff_resume', 'staff_certificate', 'staff_health_exam'))
        OR (owner_type = 'clients' AND purpose = 'client_passbook_cover')
        OR (owner_type = 'line_integration' AND purpose = 'rich_menu_background')
    );

ALTER TABLE controlled_file_objects
    DROP FOREIGN KEY fk_controlled_file_object_supersedes;

ALTER TABLE controlled_file_objects
    MODIFY COLUMN owner_type ENUM(
        'contract_signing', 'scheduling', 'orders', 'staff', 'clients', 'line_integration'
    ) NOT NULL,
    MODIFY COLUMN purpose ENUM(
        'unsigned_contract', 'final_signed_contract', 'service_date_confirmation',
        'baby_log_photo', 'meal_photo', 'order_notice', 'staff_resume',
        'staff_certificate', 'staff_health_exam', 'client_passbook_cover', 'rich_menu_background'
    ) NOT NULL,
    DROP CHECK chk_controlled_file_object_owner_purpose,
    ADD CONSTRAINT chk_controlled_file_object_owner_purpose CHECK (
        (owner_type = 'contract_signing' AND purpose IN ('unsigned_contract', 'final_signed_contract'))
        OR (owner_type = 'scheduling' AND purpose IN ('service_date_confirmation', 'baby_log_photo', 'meal_photo'))
        OR (owner_type = 'orders' AND purpose = 'order_notice')
        OR (owner_type = 'staff' AND purpose IN ('staff_resume', 'staff_certificate', 'staff_health_exam'))
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

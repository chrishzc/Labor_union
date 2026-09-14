ALTER TABLE beclass_records
    ADD COLUMN record_origin ENUM('imported', 'admin_manual') NOT NULL DEFAULT 'imported'
        AFTER bound_case_no;

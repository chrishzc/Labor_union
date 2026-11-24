ALTER TABLE staff_web_entries
    ADD COLUMN removed_at DATETIME(6) NULL,
    ADD COLUMN removed_by VARCHAR(191) NULL,
    ADD COLUMN removed_as_other BOOLEAN NOT NULL DEFAULT 0;

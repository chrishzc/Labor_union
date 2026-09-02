-- File: 1030_staff_beclass_profile.sql
-- Description: 補齊 Staff 歷史 BeClass 的教育、緊急聯絡、行政註記與資格證明保存欄位。
-- Data effect: schema_only；不推測、不回填既有 staff 業務資料。

SET @staff_education_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff'
      AND COLUMN_NAME = 'education'
);
SET @staff_education_sql = IF(
    @staff_education_exists = 0,
    'ALTER TABLE `staff` ADD COLUMN `education` VARCHAR(255) NULL COMMENT ''教育程度／最高學歷'' AFTER `address`',
    'SELECT 1'
);
PREPARE staff_beclass_profile_stmt FROM @staff_education_sql;
EXECUTE staff_beclass_profile_stmt;
DEALLOCATE PREPARE staff_beclass_profile_stmt;

SET @staff_emergency_name_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff'
      AND COLUMN_NAME = 'emergency_contact_name'
);
SET @staff_emergency_name_sql = IF(
    @staff_emergency_name_exists = 0,
    'ALTER TABLE `staff` ADD COLUMN `emergency_contact_name` VARCHAR(100) NULL COMMENT ''緊急聯絡人姓名'' AFTER `education`',
    'SELECT 1'
);
PREPARE staff_beclass_profile_stmt FROM @staff_emergency_name_sql;
EXECUTE staff_beclass_profile_stmt;
DEALLOCATE PREPARE staff_beclass_profile_stmt;

SET @staff_emergency_phone_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff'
      AND COLUMN_NAME = 'emergency_contact_phone'
);
SET @staff_emergency_phone_sql = IF(
    @staff_emergency_phone_exists = 0,
    'ALTER TABLE `staff` ADD COLUMN `emergency_contact_phone` VARCHAR(30) NULL COMMENT ''緊急聯絡人電話'' AFTER `emergency_contact_name`',
    'SELECT 1'
);
PREPARE staff_beclass_profile_stmt FROM @staff_emergency_phone_sql;
EXECUTE staff_beclass_profile_stmt;
DEALLOCATE PREPARE staff_beclass_profile_stmt;

SET @staff_admin_notes_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff'
      AND COLUMN_NAME = 'admin_notes'
);
SET @staff_admin_notes_sql = IF(
    @staff_admin_notes_exists = 0,
    'ALTER TABLE `staff` ADD COLUMN `admin_notes` TEXT NULL COMMENT ''月嫂內部行政註記'' AFTER `emergency_contact_phone`',
    'SELECT 1'
);
PREPARE staff_beclass_profile_stmt FROM @staff_admin_notes_sql;
EXECUTE staff_beclass_profile_stmt;
DEALLOCATE PREPARE staff_beclass_profile_stmt;

CREATE TABLE IF NOT EXISTS staff_certifications (
    staff_id INT NOT NULL,
    certification_type VARCHAR(191) NOT NULL COMMENT 'BeClass 資格／證明原始選項名稱',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (staff_id, certification_type),
    CONSTRAINT fk_staff_certification_staff
        FOREIGN KEY (staff_id) REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT chk_staff_certification_type
        CHECK (CHAR_LENGTH(TRIM(certification_type)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

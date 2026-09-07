-- File: 217_weekly_report_batches.sql
-- Description: 建立週報結算批次表 (weekly_report_batches) 與案件綁定表 (weekly_report_batch_cases) (方案 C 出具結算封存)。
-- Data effect: additive_only；新建表並支援每週推廣次數與詢問人次儲存，不更動既有業務表。

CREATE TABLE IF NOT EXISTS `weekly_report_batches` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `year` INT NOT NULL,
    `week_code` VARCHAR(32) NOT NULL,
    `cutoff_at` DATETIME NOT NULL,
    `promotion_count` INT NOT NULL DEFAULT 0,
    `inquiry_count` INT NOT NULL DEFAULT 0,
    `notes` TEXT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_year_week` (`year`, `week_code`),
    INDEX `idx_year` (`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `weekly_report_batch_cases` (
    `case_no` VARCHAR(64) NOT NULL PRIMARY KEY,
    `batch_id` INT NOT NULL,
    `bound_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_batch_id` (`batch_id`),
    CONSTRAINT `fk_batch_cases_batch` FOREIGN KEY (`batch_id`) REFERENCES `weekly_report_batches` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

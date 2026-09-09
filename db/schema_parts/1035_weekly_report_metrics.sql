-- File: 1035_weekly_report_metrics.sql
-- Description: preserve-data additive bridge for Monday-keyed weekly report metrics.
-- Data effect: schema_only; existing tables and rows remain unchanged.

CREATE TABLE IF NOT EXISTS `weekly_report_metrics` (
    `week_start_date` DATE NOT NULL,
    `promotion_count` INT NULL,
    `inquiry_count` INT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`week_start_date`),
    CONSTRAINT `chk_weekly_report_metrics_promotion_nonnegative`
        CHECK (`promotion_count` IS NULL OR `promotion_count` >= 0),
    CONSTRAINT `chk_weekly_report_metrics_inquiry_nonnegative`
        CHECK (`inquiry_count` IS NULL OR `inquiry_count` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

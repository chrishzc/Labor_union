-- File: 218_weekly_report_metrics.sql
-- Description: 建立以星期一為鍵的每週推廣次數與詢問人次 root fact。
-- Data effect: additive_only；不搬移、不推測也不刪除舊週報批次資料。

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

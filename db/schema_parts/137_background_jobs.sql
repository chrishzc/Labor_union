CREATE TABLE `background_jobs` (
    `job_id` VARCHAR(191) NOT NULL,
    `command_identity` VARCHAR(191) NOT NULL,
    `status` ENUM('queued', 'running', 'succeeded', 'failed', 'cancelled') NOT NULL DEFAULT 'queued',
    `receipt_payload` JSON DEFAULT NULL,
    `error_payload` JSON DEFAULT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (`job_id`),
    UNIQUE KEY `uk_command_identity` (`command_identity`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

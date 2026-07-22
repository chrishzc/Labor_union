-- 將日層級排班連回正式服務指派。既有排班一律保留 NULL，不能由 migration 推測歸屬。
SET @staff_schedule_assignment_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND COLUMN_NAME = 'assignment_id'
);
SET @staff_schedule_assignment_sql = IF(
    @staff_schedule_assignment_column_exists = 0,
    'ALTER TABLE `staff_schedule` ADD COLUMN `assignment_id` BIGINT NULL COMMENT ''正式服務指派；既有未覆核排班保留 NULL'' AFTER `staff_id`',
    'SELECT 1'
);
PREPARE staff_schedule_assignment_stmt FROM @staff_schedule_assignment_sql;
EXECUTE staff_schedule_assignment_stmt;
DEALLOCATE PREPARE staff_schedule_assignment_stmt;

SET @staff_schedule_assignment_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND INDEX_NAME = 'idx_staff_schedule_assignment'
);
SET @staff_schedule_assignment_sql = IF(
    @staff_schedule_assignment_index_exists = 0,
    'ALTER TABLE `staff_schedule` ADD INDEX `idx_staff_schedule_assignment` (`assignment_id`)',
    'SELECT 1'
);
PREPARE staff_schedule_assignment_stmt FROM @staff_schedule_assignment_sql;
EXECUTE staff_schedule_assignment_stmt;
DEALLOCATE PREPARE staff_schedule_assignment_stmt;

SET @staff_schedule_assignment_fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_schedule'
      AND CONSTRAINT_NAME = 'fk_staff_schedule_assignment'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @staff_schedule_assignment_sql = IF(
    @staff_schedule_assignment_fk_exists = 0,
    'ALTER TABLE `staff_schedule` ADD CONSTRAINT `fk_staff_schedule_assignment` FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments (id) ON UPDATE RESTRICT ON DELETE RESTRICT',
    'SELECT 1'
);
PREPARE staff_schedule_assignment_stmt FROM @staff_schedule_assignment_sql;
EXECUTE staff_schedule_assignment_stmt;
DEALLOCATE PREPARE staff_schedule_assignment_stmt;

CREATE TABLE IF NOT EXISTS staff_schedule_assignment_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    schedule_id INT NOT NULL,
    review_reason VARCHAR(100) NOT NULL,
    review_status ENUM('review_required', 'resolved') NOT NULL DEFAULT 'review_required',
    resolved_assignment_id BIGINT NULL,
    resolved_by VARCHAR(100) NULL,
    resolved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_schedule_review (schedule_id),
    INDEX idx_schedule_assignment_review_status (review_status, created_at),
    CONSTRAINT chk_schedule_assignment_review_resolution
        CHECK (
            (review_status = 'review_required'
                AND resolved_assignment_id IS NULL
                AND resolved_at IS NULL)
            OR (review_status = 'resolved'
                AND resolved_assignment_id IS NOT NULL
                AND resolved_at IS NOT NULL)
        ),
    CONSTRAINT fk_schedule_assignment_review_schedule
        FOREIGN KEY (schedule_id)
        REFERENCES staff_schedule(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_schedule_assignment_review_assignment
        FOREIGN KEY (resolved_assignment_id)
        REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

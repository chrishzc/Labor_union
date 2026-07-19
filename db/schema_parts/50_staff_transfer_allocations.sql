CREATE TABLE IF NOT EXISTS staff_transfer_allocations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    transfer_id BIGINT NOT NULL,
    settlement_detail_id BIGINT NOT NULL,
    allocated_amount DECIMAL(12, 2) NOT NULL,
    component_type ENUM(
        'regular_salary',
        'legacy_subsidy',
        'floor_fee',
        'adjustment',
        'unknown'
    ) NOT NULL DEFAULT 'unknown',
    allocation_method ENUM('explicit', 'inferred') NOT NULL DEFAULT 'explicit',
    review_status ENUM('approved', 'review_required', 'rejected')
        NOT NULL DEFAULT 'review_required',
    reversal_of_allocation_id BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_transfer_allocation_target (
        transfer_id,
        settlement_detail_id,
        component_type
    ),
    INDEX idx_staff_transfer_allocation_detail (
        settlement_detail_id,
        review_status
    ),
    CONSTRAINT chk_staff_transfer_allocation_amount
        CHECK (allocated_amount > 0),
    CONSTRAINT chk_staff_transfer_allocation_inference_review
        CHECK (
            allocation_method <> 'inferred'
            OR review_status <> 'approved'
        ),
    CONSTRAINT fk_staff_transfer_allocation_transfer
        FOREIGN KEY (transfer_id)
        REFERENCES staff_actual_transfers(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_staff_transfer_allocation_detail
        FOREIGN KEY (settlement_detail_id)
        REFERENCES staff_monthly_settlement_details(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_staff_transfer_allocation_reversal
        FOREIGN KEY (reversal_of_allocation_id)
        REFERENCES staff_transfer_allocations(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 既有資料庫可能仍使用 transfer/detail 兩欄唯一鍵。依實際欄位順序調整
-- 索引，讓 migration 可重跑；ALTER 僅改索引，不改寫既有 allocation 資料。
SET @staff_transfer_allocation_target_columns = (
    SELECT GROUP_CONCAT(
        COLUMN_NAME
        ORDER BY SEQ_IN_INDEX
        SEPARATOR ','
    )
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'staff_transfer_allocations'
      AND INDEX_NAME = 'uq_staff_transfer_allocation_target'
);
SET @staff_transfer_allocation_index_sql = CASE
    WHEN @staff_transfer_allocation_target_columns =
         'transfer_id,settlement_detail_id' THEN
        'ALTER TABLE `staff_transfer_allocations` DROP INDEX `uq_staff_transfer_allocation_target`, ADD UNIQUE KEY `uq_staff_transfer_allocation_target` (`transfer_id`, `settlement_detail_id`, `component_type`)'
    WHEN @staff_transfer_allocation_target_columns IS NULL THEN
        'ALTER TABLE `staff_transfer_allocations` ADD UNIQUE KEY `uq_staff_transfer_allocation_target` (`transfer_id`, `settlement_detail_id`, `component_type`)'
    ELSE 'SELECT 1'
END;
PREPARE staff_transfer_allocation_index_stmt
    FROM @staff_transfer_allocation_index_sql;
EXECUTE staff_transfer_allocation_index_stmt;
DEALLOCATE PREPARE staff_transfer_allocation_index_stmt;

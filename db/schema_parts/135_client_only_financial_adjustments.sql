-- Add explicit client-only financial adjustments without payroll side effects.

SET @financial_adjustment_scope_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'financial_adjustments'
      AND COLUMN_NAME = 'adjustment_scope'
);
SET @financial_adjustment_scope_sql = IF(
    @financial_adjustment_scope_exists = 0,
    'ALTER TABLE financial_adjustments ADD COLUMN adjustment_scope ENUM(''client_only'',''client_and_staff'') NOT NULL DEFAULT ''client_and_staff'' AFTER adjustment_source_type',
    'SELECT 1'
);
PREPARE financial_adjustment_scope_statement
    FROM @financial_adjustment_scope_sql;
EXECUTE financial_adjustment_scope_statement;
DEALLOCATE PREPARE financial_adjustment_scope_statement;

ALTER TABLE financial_adjustment_apply_receipts
    MODIFY COLUMN resulting_payroll_version BIGINT UNSIGNED NULL;

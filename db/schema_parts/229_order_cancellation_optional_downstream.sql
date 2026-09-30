-- Allow absent downstream owners without fabricating cancellation history.
ALTER TABLE order_cancellation_apply_receipts
    MODIFY COLUMN scheduling_command_receipt_id BIGINT NULL,
    MODIFY COLUMN scheduling_version BIGINT UNSIGNED NULL,
    MODIFY COLUMN scheduling_generation INT UNSIGNED NULL,
    MODIFY COLUMN client_finance_version BIGINT UNSIGNED NULL,
    MODIFY COLUMN payroll_version BIGINT UNSIGNED NULL;

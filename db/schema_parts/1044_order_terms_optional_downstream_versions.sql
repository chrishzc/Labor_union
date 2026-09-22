ALTER TABLE order_terms_apply_receipts
    MODIFY COLUMN client_finance_version BIGINT UNSIGNED NULL,
    MODIFY COLUMN payroll_version BIGINT UNSIGNED NULL;

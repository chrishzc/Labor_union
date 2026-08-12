-- Bootstrap may adopt an already-versioned Scheduling aggregate. Finance and
-- Payroll roots are still created at version zero by this transaction.
ALTER TABLE case_architecture_bootstrap_receipts
    DROP CHECK chk_case_architecture_receipt_initial_versions;

ALTER TABLE case_architecture_bootstrap_receipts
    ADD CONSTRAINT chk_case_architecture_receipt_bootstrap_versions
    CHECK (
        client_finance_version = 0
        AND payroll_version = 0
    );

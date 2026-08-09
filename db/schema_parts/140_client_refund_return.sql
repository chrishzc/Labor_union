-- Add the distinct idempotency receipt kind for a bank-backed client refund return.

ALTER TABLE client_refund_reversal_apply_receipts
    MODIFY COLUMN correction_type ENUM('refund', 'refund_return', 'reversal') NOT NULL;

ALTER TABLE client_ledger_entries
    DROP CHECK chk_client_ledger_reversal_shape,
    ADD CONSTRAINT chk_client_ledger_reversal_shape CHECK (
        (entry_type IN (
            'reversal',
            'refund_reversal',
            'subsidy_return_reversal',
            'subsidy_advance_reversal'
        ) AND reversal_of_entry_id IS NOT NULL)
        OR (entry_type NOT IN (
            'reversal',
            'refund_reversal',
            'subsidy_return_reversal',
            'subsidy_advance_reversal'
        ) AND reversal_of_entry_id IS NULL)
    );

ALTER TABLE finance_import_classification_events
    MODIFY COLUMN classification_type ENUM(
        'client_receipt',
        'client_refund',
        'client_refund_return',
        'client_subsidy_return',
        'government_subsidy',
        'staff_payout',
        'non_business_review'
    ) NOT NULL;

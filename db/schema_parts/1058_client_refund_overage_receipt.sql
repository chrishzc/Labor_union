-- Complete the already-supported Client Finance REFUND_OVERAGE writer contract.
-- Append only: preserve the ordinal and value of all existing receipt kinds.
ALTER TABLE client_refund_reversal_apply_receipts
    MODIFY COLUMN correction_type ENUM('refund', 'refund_return', 'reversal', 'refund_overage') NOT NULL;

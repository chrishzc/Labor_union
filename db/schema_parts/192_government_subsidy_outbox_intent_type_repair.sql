-- File: 192_government_subsidy_outbox_intent_type_repair.sql
-- Description: 補齊政府補助 outbox 的 overpayment disposition intent enum。

ALTER TABLE government_subsidy_outbox
    MODIFY COLUMN intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_receipt_allocated',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed',
        'government_subsidy_overpayment_established',
        'government_subsidy_overpayment_offset',
        'government_overpayment_return_payable',
        'government_overpayment_return_payout'
    ) NOT NULL;

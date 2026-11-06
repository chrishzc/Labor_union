-- Staff Payables source provenance for the manual supplement exception (spec 22 section 19).
-- Preserve all existing event values: the default does not assert a bank/manual origin.
-- Keep the original account hash CHECK, immutable guards, links and foreign keys.
ALTER TABLE staff_payout_events
    ADD COLUMN payment_source_kind ENUM(
        'legacy_unspecified', 'bank_statement', 'manual_supplement'
    ) NOT NULL DEFAULT 'legacy_unspecified',
    MODIFY COLUMN bank_account_identity_hash CHAR(64) NULL,
    ADD CONSTRAINT chk_staff_payout_payment_source CHECK (
        (payment_source_kind IN ('legacy_unspecified', 'bank_statement')
         AND bank_account_identity_hash IS NOT NULL
         AND bank_account_identity_hash REGEXP '^[0-9a-f]{64}$')
        OR (payment_source_kind = 'manual_supplement'
            AND bank_account_identity_hash IS NULL)
    );

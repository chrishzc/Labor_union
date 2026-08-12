-- Holiday Query can produce an approved Scheduling change without a manual
-- leave item. Preview fingerprint and fresh-fact checks remain the Apply gate.
ALTER TABLE scheduling_leave_substitution_batches
    DROP CHECK chk_scheduling_leave_batch_identity;

ALTER TABLE scheduling_leave_substitution_batches
    ADD CONSTRAINT chk_scheduling_leave_batch_identity
    CHECK (
        item_count >= 0
        AND CHAR_LENGTH(TRIM(batch_key)) > 0
        AND CHAR_LENGTH(TRIM(actor)) > 0
        AND CHAR_LENGTH(TRIM(reason)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    );

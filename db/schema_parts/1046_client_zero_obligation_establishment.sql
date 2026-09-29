-- Preserve zero-amount initial obligations and their settlement/source lineage.
-- Schema only: no existing amount, due date, event or projection is rewritten.
ALTER TABLE client_obligation_events
    DROP CHECK chk_client_obligation_event_amount,
    ADD CONSTRAINT chk_client_obligation_event_amount CHECK (
        before_amount_ntd >= 0
        AND after_amount_ntd >= 0
        AND (
            before_amount_ntd <> after_amount_ntd
            OR NOT (before_due_date <=> after_due_date)
            OR (
                event_type = 'established'
                AND before_amount_ntd = 0
                AND after_amount_ntd = 0
                AND before_due_date IS NULL
                AND after_due_date IS NULL
            )
        )
    );

-- Keep the human reopen note optional under Global 2.4; preserve every row.
-- Retain the command, actor and correlation checks on the same immutable event.
ALTER TABLE order_reopen_events
    DROP CHECK chk_order_reopen_event_text,
    ADD CONSTRAINT chk_order_reopen_event_text CHECK (
        CHAR_LENGTH(TRIM(idempotency_key)) > 0
        AND CHAR_LENGTH(TRIM(actor)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    );

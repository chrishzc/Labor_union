-- Keep the optional reason as supplied while retaining required audit metadata.
ALTER TABLE case_architecture_bootstrap_events
    DROP CHECK chk_case_architecture_bootstrap_text,
    ADD CONSTRAINT chk_case_architecture_bootstrap_text CHECK (
        CHAR_LENGTH(TRIM(source_identity_status)) > 0
        AND CHAR_LENGTH(TRIM(actor)) > 0
        AND CHAR_LENGTH(TRIM(correlation_id)) > 0
    );

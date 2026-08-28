-- Add independent, auditable evidence references to manual finance recovery actions.

ALTER TABLE client_over_refund_recovery_events
    ADD COLUMN evidence_reference VARCHAR(500) NULL AFTER reason,
    ADD CONSTRAINT chk_client_over_refund_recovery_event_evidence
        CHECK (
            evidence_reference IS NULL
            OR CHAR_LENGTH(TRIM(evidence_reference)) > 0
        );

ALTER TABLE client_over_refund_recovery_matchings
    ADD COLUMN evidence_reference VARCHAR(500) NULL AFTER reason,
    ADD CONSTRAINT chk_client_over_refund_recovery_matching_evidence
        CHECK (
            evidence_reference IS NULL
            OR CHAR_LENGTH(TRIM(evidence_reference)) > 0
        );

ALTER TABLE staff_overpayment_recovery_events
    ADD COLUMN evidence_reference VARCHAR(500) NULL AFTER reason,
    ADD CONSTRAINT chk_staff_overpayment_recovery_event_evidence
        CHECK (
            evidence_reference IS NULL
            OR CHAR_LENGTH(TRIM(evidence_reference)) > 0
        );

ALTER TABLE staff_overpayment_recovery_matchings
    ADD COLUMN evidence_reference VARCHAR(500) NULL AFTER reason,
    ADD CONSTRAINT chk_staff_overpayment_recovery_matching_evidence
        CHECK (
            evidence_reference IS NULL
            OR CHAR_LENGTH(TRIM(evidence_reference)) > 0
        );

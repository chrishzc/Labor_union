-- File: 1034_contract_external_signing_final_pdf_completion.sql
-- Purpose: align the external-signing session constraint with final-PDF completion.
-- Data effect: schema only; existing session rows and optional audit reports are preserved.

ALTER TABLE contract_external_signing_sessions
    DROP CHECK chk_contract_external_session_state,
    ADD CONSTRAINT chk_contract_external_session_state CHECK (
        (session_state = 'staff_reporting' AND commitment_id IS NULL)
        OR (session_state IN (
                'staff_reports_complete',
                'client_reported_final_pdf_pending',
                'completed'
            ) AND commitment_id IS NOT NULL)
        OR session_state = 'superseded'
    );

-- File: 214_historical_order_pairing_resolution_reused.sql
-- Purpose: allow historical-order evidence to persist a reused assignment pairing.
-- Data effect: schema only; existing pairing evidence remains readable.

ALTER TABLE historical_order_pairing_evidence
    MODIFY COLUMN resolution ENUM(
        'blank',
        'staff_missing',
        'staff_ambiguous',
        'evidence_only',
        'assignment_candidate',
        'assignment_reused',
        'assignment_conflict'
    ) NOT NULL;

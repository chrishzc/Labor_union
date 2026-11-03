-- Allow both newly created and reused assignment evidence; preserve every existing row.
ALTER TABLE historical_order_pairing_evidence
    DROP CHECK chk_historical_order_pairing_assignment_shape,
    ADD CONSTRAINT chk_historical_order_pairing_assignment_shape CHECK (
        (resolution IN ('assignment_candidate','assignment_reused')
         AND assignment_id IS NOT NULL AND staff_id IS NOT NULL)
        OR
        (resolution NOT IN ('assignment_candidate','assignment_reused')
         AND assignment_id IS NULL)
    );

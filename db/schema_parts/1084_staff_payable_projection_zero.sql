-- Keep the effective payable projection when a correction reduces the entitlement to zero.
ALTER TABLE staff_payable_projections
    DROP CHECK chk_staff_payable_projection_money,
    ADD CONSTRAINT chk_staff_payable_projection_money CHECK (
        obligation_amount_ntd >= 0
        AND net_paid_ntd >= 0
        AND balance_ntd = obligation_amount_ntd - net_paid_ntd
    );

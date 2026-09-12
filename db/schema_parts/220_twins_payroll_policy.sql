-- Add the canonical twins Payroll policy to fresh schema assembly.

ALTER TABLE assignment_payroll_rate_snapshots
    DROP FOREIGN KEY fk_assignment_payroll_rate_policy;

ALTER TABLE case_architecture_bootstrap_events
    DROP FOREIGN KEY fk_case_architecture_bootstrap_payroll_policy;

ALTER TABLE case_payroll_rate_policy_snapshots
    DROP FOREIGN KEY fk_case_payroll_policy_definition;

ALTER TABLE payroll_rate_policies
    MODIFY COLUMN policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen',
        'twins'
    ) NOT NULL;

INSERT INTO payroll_rate_policies (
    policy_version,
    policy_kind,
    hourly_rate_ntd,
    effective_from,
    effective_until
)
SELECT 'approved-rates-v1', 'twins', 450, '1900-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM payroll_rate_policies
    WHERE policy_version = 'approved-rates-v1'
      AND policy_kind = 'twins'
);

ALTER TABLE assignment_payroll_rate_snapshots
    MODIFY COLUMN policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen',
        'twins'
    ) NOT NULL;

ALTER TABLE case_architecture_bootstrap_events
    MODIFY COLUMN payroll_policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen',
        'twins'
    ) NOT NULL;

ALTER TABLE case_payroll_rate_policy_snapshots
    MODIFY COLUMN policy_kind ENUM(
        'citizen',
        'subsidized_citizen',
        'non_citizen',
        'twins'
    ) NOT NULL;

ALTER TABLE assignment_payroll_rate_snapshots
    ADD CONSTRAINT fk_assignment_payroll_rate_policy
        FOREIGN KEY (policy_version, policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE case_architecture_bootstrap_events
    ADD CONSTRAINT fk_case_architecture_bootstrap_payroll_policy
        FOREIGN KEY (payroll_policy_version, payroll_policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

ALTER TABLE case_payroll_rate_policy_snapshots
    ADD CONSTRAINT fk_case_payroll_policy_definition
        FOREIGN KEY (policy_version, policy_kind)
        REFERENCES payroll_rate_policies(policy_version, policy_kind)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

-- Additive pricing policy and explicit per-case overrides. No financial backfill.
CREATE TABLE IF NOT EXISTS accounting_pricing_state (
    singleton_id TINYINT NOT NULL,
    revision BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY(singleton_id),
    CONSTRAINT chk_accounting_pricing_singleton CHECK (singleton_id=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO accounting_pricing_state(singleton_id,revision) SELECT 1,0 WHERE NOT EXISTS (SELECT 1 FROM accounting_pricing_state WHERE singleton_id=1);

CREATE TABLE IF NOT EXISTS accounting_pricing_policies (
    id BIGINT NOT NULL,
    effective_on DATE NOT NULL,
    policy_json JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL,
    PRIMARY KEY(id),
    KEY ix_accounting_pricing_effective(effective_on,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_pricing_events (
    id BIGINT NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL,
    resulting_revision BIGINT NOT NULL,
    pricing_json JSON NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL,
    PRIMARY KEY(id),
    UNIQUE KEY uq_case_pricing_revision(case_no,resulting_revision),
    CONSTRAINT fk_case_pricing_order FOREIGN KEY(case_no) REFERENCES orders(case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE orders
    ADD COLUMN pricing_policy_id BIGINT NULL,
    ADD COLUMN pricing_override_event_id BIGINT NULL,
    ADD COLUMN pricing_revision BIGINT NOT NULL DEFAULT 0,
    ADD KEY ix_orders_pricing_policy(pricing_policy_id),
    ADD KEY ix_orders_pricing_override(pricing_override_event_id),
    ADD CONSTRAINT fk_order_pricing_policy FOREIGN KEY(pricing_policy_id) REFERENCES accounting_pricing_policies(id),
    ADD CONSTRAINT fk_order_pricing_override FOREIGN KEY(pricing_override_event_id) REFERENCES case_pricing_events(id);

CREATE TABLE IF NOT EXISTS accounting_pricing_receipts (
    idempotency_key VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    command_hash CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    result_json JSON NOT NULL,
    created_at_utc DATETIME(6) NOT NULL,
    PRIMARY KEY(idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_obligation_installments (
    obligation_identity VARCHAR(191) NOT NULL,
    funding_kind ENUM('client','subsidy') NOT NULL,
    amount_ntd BIGINT NOT NULL,
    due_date DATE NULL,
    PRIMARY KEY(obligation_identity,funding_kind),
    CONSTRAINT fk_payroll_installment_obligation FOREIGN KEY(obligation_identity) REFERENCES staff_obligations(obligation_identity),
    CONSTRAINT chk_payroll_installment_amount CHECK(amount_ntd>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Read-only extraction of the bound immutable policy/current explicit override.
-- No fees, payroll or subsidy amounts are calculated by this view.
CREATE OR REPLACE VIEW case_pricing_facts AS
SELECT o.case_no,
       1 AS pricing_active,
       (e.id IS NOT NULL) AS pricing_override_active,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.rule')),i.rule_name) AS pricing_rule,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.subsidy_hours')),i.subsidy_hours) AS pricing_subsidy_hours,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.client.covered')),i.client_covered) AS pricing_client_covered,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.client.excess')),i.client_excess) AS pricing_client_excess,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.payroll.covered')),i.payroll_covered) AS pricing_payroll_covered,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.payroll.excess')),i.payroll_excess) AS pricing_payroll_excess,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.payroll.covered')),JSON_UNQUOTE(JSON_EXTRACT(p.policy_json,'$.twins_payroll.covered'))) AS pricing_twins_payroll_covered
FROM orders o
JOIN clients c ON c.id=o.client_id
LEFT JOIN accounting_pricing_policies p ON p.id=o.pricing_policy_id
LEFT JOIN JSON_TABLE(p.policy_json,'$.identities[*]' COLUMNS (
    identity_name VARCHAR(100) PATH '$.identity_name',
    rule_name VARCHAR(20) PATH '$.rule',
    subsidy_hours VARCHAR(100) PATH '$.subsidy_hours',
    client_covered VARCHAR(30) PATH '$.client.covered',
    client_excess VARCHAR(30) PATH '$.client.excess',
    payroll_covered VARCHAR(30) PATH '$.payroll.covered',
    payroll_excess VARCHAR(30) PATH '$.payroll.excess'
)) i ON i.identity_name COLLATE utf8mb4_unicode_ci=(CASE c.identity_status
    WHEN '一般市民' THEN '補助市民' WHEN '低收入戶' THEN '社福' WHEN '中低收入戶' THEN '社福'
    ELSE c.identity_status END) COLLATE utf8mb4_unicode_ci
LEFT JOIN case_pricing_events e ON e.id=o.pricing_override_event_id AND e.case_no=o.case_no
WHERE o.pricing_policy_id IS NOT NULL OR o.pricing_override_event_id IS NOT NULL;

-- Additive Client Finance-owned current deposit settlement projection.

CREATE TABLE IF NOT EXISTS client_deposit_settlement_projection (
    case_no VARCHAR(50) PRIMARY KEY,
    deposit_obligation_identity VARCHAR(191) NOT NULL,
    settlement_state ENUM('unsettled', 'settled') NOT NULL,
    contracted_amount_ntd BIGINT UNSIGNED NOT NULL,
    allocated_net_amount_ntd BIGINT NOT NULL,
    settlement_identity CHAR(64) NULL,
    source_fingerprint CHAR(64) NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    latest_ledger_entry_id BIGINT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_deposit_projection_obligation (
        deposit_obligation_identity,
        case_no
    ),
    INDEX idx_client_deposit_projection_state (
        settlement_state,
        case_no
    ),
    CONSTRAINT fk_client_deposit_projection_account
        FOREIGN KEY (case_no) REFERENCES client_finance_accounts(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_deposit_projection_obligation
        FOREIGN KEY (deposit_obligation_identity, case_no)
        REFERENCES client_obligations(obligation_identity, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_deposit_projection_latest_ledger
        FOREIGN KEY (latest_ledger_entry_id) REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_deposit_projection_version
        CHECK (projection_version > 0),
    CONSTRAINT chk_client_deposit_projection_amount
        CHECK (contracted_amount_ntd > 0),
    CONSTRAINT chk_client_deposit_projection_fingerprints
        CHECK (
            source_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND (
                settlement_identity IS NULL
                OR settlement_identity REGEXP '^[0-9a-f]{64}$'
            )
        ),
    CONSTRAINT chk_client_deposit_projection_state
        CHECK (
            (
                settlement_state = 'settled'
                AND allocated_net_amount_ntd = contracted_amount_ntd
                AND settlement_identity IS NOT NULL
                AND latest_ledger_entry_id IS NOT NULL
            )
            OR
            (
                settlement_state = 'unsettled'
                AND allocated_net_amount_ntd <> contracted_amount_ntd
                AND settlement_identity IS NULL
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

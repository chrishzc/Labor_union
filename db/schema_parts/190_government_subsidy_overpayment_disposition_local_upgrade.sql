-- Immutable root and disposition lineage for government subsidy overpayments.

CREATE TABLE IF NOT EXISTS government_payers (
    payer_identity VARCHAR(191) PRIMARY KEY,
    payer_name VARCHAR(191) NOT NULL,
    incoming_memo_match VARCHAR(191) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_government_payer_identity
        CHECK (payer_identity = 'hccg'),
    CONSTRAINT chk_government_payer_name
        CHECK (payer_name = '新竹市政府'),
    CONSTRAINT chk_government_payer_memo
        CHECK (incoming_memo_match = '新竹市政府')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO government_payers (payer_identity,payer_name,incoming_memo_match,is_active)
VALUES ('hccg','新竹市政府','新竹市政府',1)
ON DUPLICATE KEY UPDATE payer_name=VALUES(payer_name),
    incoming_memo_match=VALUES(incoming_memo_match),is_active=VALUES(is_active);

CREATE TABLE IF NOT EXISTS government_payer_receiving_accounts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    payer_identity VARCHAR(191) NOT NULL,
    bank_code VARCHAR(32) NOT NULL,
    account_number VARCHAR(191) NOT NULL,
    account_name VARCHAR(191) NOT NULL,
    effective_from DATE NOT NULL,
    effective_until DATE NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_payer_account_version (payer_identity, effective_from),
    INDEX idx_government_payer_active_account (payer_identity, effective_from, effective_until),
    CONSTRAINT fk_government_payer_account_payer
        FOREIGN KEY (payer_identity) REFERENCES government_payers(payer_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_payer_account_period
        CHECK (effective_until IS NULL OR effective_until >= effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayments (
    overpayment_identity VARCHAR(191) PRIMARY KEY,
    source_finance_import_row_id BIGINT NOT NULL,
    source_transaction_id BIGINT NOT NULL,
    payer_identity VARCHAR(191) NOT NULL,
    original_amount_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM(
        'pending_review', 'offset_reserved', 'offset_applied',
        'return_payable', 'partially_returned', 'returned'
    ) NOT NULL DEFAULT 'pending_review',
    projection_version BIGINT UNSIGNED NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_overpayment_bank_row (source_finance_import_row_id),
    UNIQUE KEY uq_government_subsidy_overpayment_transaction (source_transaction_id),
    INDEX idx_government_subsidy_overpayment_status (status, created_at),
    CONSTRAINT fk_government_subsidy_overpayment_bank_row
        FOREIGN KEY (source_finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_overpayment_transaction
        FOREIGN KEY (source_transaction_id) REFERENCES government_subsidy_transactions(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_overpayment_amount
        CHECK (
            original_amount_ntd > 0
            AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= original_amount_ntd
            AND (
                remaining_amount_ntd > 0
                OR status IN ('offset_applied', 'returned')
            )
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_identity VARCHAR(191) NOT NULL,
    event_type ENUM(
        'established',
        'offset_applied',
        'return_payable_created',
        'return_paid',
        'return_reconciled'
    ) NOT NULL,
    before_remaining_ntd BIGINT NOT NULL,
    after_remaining_ntd BIGINT NOT NULL,
    resulting_status VARCHAR(32) NOT NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_overpayment_event_idempotency (idempotency_key),
    INDEX idx_government_subsidy_overpayment_event_root (overpayment_identity, id),
    CONSTRAINT fk_government_subsidy_overpayment_event_root
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_overpayment_event_amount
        CHECK (before_remaining_ntd > 0 AND after_remaining_ntd >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_offsets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_event_id BIGINT NOT NULL,
    overpayment_identity VARCHAR(191) NOT NULL,
    claim_batch_id BIGINT NOT NULL,
    claim_item_id BIGINT NOT NULL,
    allocated_amount_ntd BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_subsidy_overpayment_offset_target (overpayment_identity, claim_item_id),
    INDEX idx_government_subsidy_overpayment_offset_item (claim_batch_id, claim_item_id),
    CONSTRAINT fk_government_subsidy_overpayment_offset_event
        FOREIGN KEY (overpayment_event_id) REFERENCES government_subsidy_overpayment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_overpayment_offset_root
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_subsidy_overpayment_offset_item
        FOREIGN KEY (claim_item_id, claim_batch_id) REFERENCES subsidy_claim_batch_items(id, batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_subsidy_overpayment_offset_amount CHECK (allocated_amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_subsidy_overpayment_target_projection_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_event_id BIGINT NOT NULL,
    batch_id BIGINT NOT NULL,
    before_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    after_net_allocated_ntd BIGINT UNSIGNED NOT NULL,
    outstanding_ntd BIGINT UNSIGNED NOT NULL,
    expected_batch_version BIGINT UNSIGNED NOT NULL,
    resulting_batch_version BIGINT UNSIGNED NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_target_projection (
        overpayment_event_id, batch_id
    ),
    CONSTRAINT fk_government_overpayment_target_projection_event
        FOREIGN KEY (overpayment_event_id)
        REFERENCES government_subsidy_overpayment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_overpayment_target_projection_batch
        FOREIGN KEY (batch_id) REFERENCES government_subsidy_batch_accounts(batch_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_target_projection_version
        CHECK (resulting_batch_version = expected_batch_version + 1),
    CONSTRAINT chk_government_overpayment_target_projection_amount
        CHECK (after_net_allocated_ntd >= before_net_allocated_ntd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_overpayment_return_payables (
    payable_identity VARCHAR(191) PRIMARY KEY,
    overpayment_identity VARCHAR(191) NOT NULL,
    amount_due_ntd BIGINT NOT NULL,
    remaining_amount_ntd BIGINT NOT NULL,
    status ENUM('payable', 'partially_paid', 'paid') NOT NULL DEFAULT 'payable',
    agency_identity VARCHAR(191) NOT NULL,
    agency_name VARCHAR(191) NOT NULL,
    bank_code VARCHAR(32) NOT NULL,
    account_display VARCHAR(191) NOT NULL,
    account_fingerprint CHAR(64) NOT NULL,
    effective_date DATE NOT NULL,
    due_date DATE NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    projection_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_return_root (overpayment_identity),
    INDEX idx_government_overpayment_return_due (status, due_date),
    CONSTRAINT fk_government_overpayment_return_root
        FOREIGN KEY (overpayment_identity) REFERENCES government_subsidy_overpayments(overpayment_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_return_amount
        CHECK (
            amount_due_ntd > 0
            AND remaining_amount_ntd >= 0
            AND remaining_amount_ntd <= amount_due_ntd
            AND (remaining_amount_ntd > 0 OR status = 'paid')
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS government_overpayment_return_payouts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    overpayment_event_id BIGINT NOT NULL,
    payable_identity VARCHAR(191) NOT NULL,
    finance_import_row_id BIGINT NOT NULL,
    amount_ntd BIGINT NOT NULL,
    preview_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_government_overpayment_return_payout_bank (finance_import_row_id),
    UNIQUE KEY uq_government_overpayment_return_payout_key (idempotency_key),
    CONSTRAINT fk_government_overpayment_return_payout_event
        FOREIGN KEY (overpayment_event_id) REFERENCES government_subsidy_overpayment_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_overpayment_return_payout_payable
        FOREIGN KEY (payable_identity) REFERENCES government_overpayment_return_payables(payable_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_government_overpayment_return_payout_bank
        FOREIGN KEY (finance_import_row_id) REFERENCES finance_import_rows(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_government_overpayment_return_payout_amount CHECK (amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_government_subsidy_overpayment_events_before_update;
CREATE TRIGGER trg_government_subsidy_overpayment_events_before_update
BEFORE UPDATE ON government_subsidy_overpayment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_subsidy_overpayment_events_before_delete;
CREATE TRIGGER trg_government_subsidy_overpayment_events_before_delete
BEFORE DELETE ON government_subsidy_overpayment_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_events records cannot be deleted';

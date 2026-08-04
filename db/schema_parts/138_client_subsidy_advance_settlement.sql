-- Additive settlement facts for a union-funded client subsidy advance.

ALTER TABLE client_ledger_entries
    MODIFY COLUMN entry_type ENUM(
        'receipt',
        'refund',
        'subsidy_return',
        'subsidy_advance',
        'adjustment',
        'reversal',
        'refund_reversal',
        'subsidy_return_reversal',
        'subsidy_advance_reversal'
    ) NOT NULL;

ALTER TABLE government_subsidy_outbox
    MODIFY COLUMN intent_type ENUM(
        'government_subsidy_receipt_applied',
        'government_subsidy_receipt_allocated',
        'government_subsidy_reversal_applied',
        'government_subsidy_anomaly_root_changed'
    ) NOT NULL;

CREATE TABLE IF NOT EXISTS client_subsidy_return_claim_item_links (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    obligation_identity VARCHAR(191) NOT NULL,
    claim_item_id BIGINT NOT NULL,
    entitled_amount_ntd BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_subsidy_return_claim_item (
        obligation_identity,
        claim_item_id
    ),
    INDEX idx_client_subsidy_return_claim_item (claim_item_id),
    CONSTRAINT fk_client_subsidy_return_link_obligation
        FOREIGN KEY (obligation_identity)
        REFERENCES client_obligations(obligation_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_return_link_claim_item
        FOREIGN KEY (claim_item_id)
        REFERENCES subsidy_claim_batch_items(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_subsidy_return_link_amount
        CHECK (entitled_amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_subsidy_advance_recoveries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    advance_ledger_entry_id BIGINT NOT NULL,
    government_allocation_id BIGINT NOT NULL,
    recovered_amount_ntd BIGINT UNSIGNED NOT NULL,
    source_outbox_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_client_subsidy_advance_recovery (
        advance_ledger_entry_id,
        government_allocation_id
    ),
    UNIQUE KEY uq_client_subsidy_advance_once (
        advance_ledger_entry_id
    ),
    UNIQUE KEY uq_client_subsidy_recovery_outbox_advance (
        source_outbox_id,
        advance_ledger_entry_id
    ),
    INDEX idx_client_subsidy_recovery_case (case_no, created_at),
    CONSTRAINT fk_client_subsidy_recovery_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_recovery_advance
        FOREIGN KEY (advance_ledger_entry_id)
        REFERENCES client_ledger_entries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_recovery_allocation
        FOREIGN KEY (government_allocation_id)
        REFERENCES government_subsidy_allocations(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_client_subsidy_recovery_outbox
        FOREIGN KEY (source_outbox_id)
        REFERENCES government_subsidy_outbox(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_client_subsidy_recovery_amount
        CHECK (recovered_amount_ntd > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_client_subsidy_advance_recovery_before_update;
CREATE TRIGGER trg_client_subsidy_advance_recovery_before_update
BEFORE UPDATE ON client_subsidy_advance_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be updated';

DROP TRIGGER IF EXISTS trg_client_subsidy_advance_recovery_before_delete;
CREATE TRIGGER trg_client_subsidy_advance_recovery_before_delete
BEFORE DELETE ON client_subsidy_advance_recoveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be deleted';

DROP TRIGGER IF EXISTS trg_client_subsidy_return_claim_item_link_before_update;
CREATE TRIGGER trg_client_subsidy_return_claim_item_link_before_update
BEFORE UPDATE ON client_subsidy_return_claim_item_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be updated';

DROP TRIGGER IF EXISTS trg_client_subsidy_return_claim_item_link_before_delete;
CREATE TRIGGER trg_client_subsidy_return_claim_item_link_before_delete
BEFORE DELETE ON client_subsidy_return_claim_item_links
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be deleted';

-- 服務人員實際銀行轉帳事件。
-- 每筆銀行流水只保存一次；跨訂單分配由獨立 allocation schema 負責。
CREATE TABLE IF NOT EXISTS staff_actual_transfers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    settlement_id BIGINT NOT NULL,
    staff_id INT NOT NULL,
    payment_phase ENUM('normal', 'first_salary', 'second_subsidy', 'unknown')
        NOT NULL DEFAULT 'unknown',
    transaction_type ENUM('transfer', 'return', 'reversal') NOT NULL,
    transaction_status ENUM('succeeded', 'failed', 'reversed')
        NOT NULL DEFAULT 'succeeded',
    amount DECIMAL(12, 2) NOT NULL,
    occurred_at DATE NULL,
    source_bank VARCHAR(100) NOT NULL,
    source_account VARCHAR(100) NULL,
    counterparty_account VARCHAR(100) NULL,
    external_reference VARCHAR(191) NOT NULL,
    reversal_of_transfer_id BIGINT NULL,
    raw_import_reference VARCHAR(255) NULL,
    review_status ENUM('not_required', 'pending', 'confirmed')
        NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_staff_actual_transfer_reference UNIQUE (external_reference),
    INDEX idx_staff_actual_transfer_settlement (settlement_id, occurred_at),
    INDEX idx_staff_actual_transfer_staff (staff_id, occurred_at),
    INDEX idx_staff_actual_transfer_reversal (reversal_of_transfer_id),

    CONSTRAINT fk_staff_actual_transfer_settlement
        FOREIGN KEY (settlement_id)
        REFERENCES staff_monthly_settlements(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_actual_transfer_staff
        FOREIGN KEY (staff_id)
        REFERENCES staff(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_staff_actual_transfer_reversal
        FOREIGN KEY (reversal_of_transfer_id)
        REFERENCES staff_actual_transfers(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT chk_staff_actual_transfer_amount
        CHECK (amount > 0),
    CONSTRAINT chk_staff_actual_transfer_succeeded_date
        CHECK (transaction_status <> 'succeeded' OR occurred_at IS NOT NULL),
    CONSTRAINT chk_staff_actual_transfer_original
        CHECK (
            (transaction_type = 'transfer' AND reversal_of_transfer_id IS NULL)
            OR
            (transaction_type IN ('return', 'reversal') AND reversal_of_transfer_id IS NOT NULL)
        ),
    CONSTRAINT chk_staff_actual_transfer_unknown_review
        CHECK (payment_phase <> 'unknown' OR review_status = 'pending')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 104_order_lifecycle_state_history.sql
-- 記錄訂單生命週期的狀態轉移、明確維持或阻擋決策。
-- 本 schema 僅新增 append-only 歷史結構，不回填或修改任何既有正式資料。

CREATE TABLE IF NOT EXISTS order_lifecycle_state_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    case_no VARCHAR(50) NOT NULL COMMENT '事件所屬訂單（對應 orders.case_no）',
    trigger_event VARCHAR(100) NOT NULL COMMENT '觸發本次狀態評估的事件名稱',
    before_status VARCHAR(20) NOT NULL COMMENT '狀態評估前的 canonical 訂單狀態',
    after_status VARCHAR(20) NOT NULL COMMENT '狀態評估後的 canonical 訂單狀態；維持或阻擋時可與 before_status 相同',
    actor VARCHAR(255) NOT NULL COMMENT '觸發事件的操作者或系統身分',
    business_date DATE NOT NULL COMMENT '狀態評估採用的業務日期',
    expected_version BIGINT UNSIGNED NOT NULL COMMENT '呼叫端進行樂觀鎖定時讀取的訂單版本',
    idempotency_key VARCHAR(191) NOT NULL COMMENT '同一訂單內唯一的呼叫端冪等鍵',
    facts_snapshot JSON NOT NULL COMMENT '狀態評估當下的權威事實與決策摘要',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '事件建立時間',
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_lifecycle_state_event_idempotency (
        case_no,
        idempotency_key
    ),
    INDEX idx_order_lifecycle_state_event_case_time (
        case_no,
        created_at
    ),
    CONSTRAINT fk_order_lifecycle_state_event_case_no
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_lifecycle_state_event_before_status
        CHECK (
            before_status IN (
                '洽談中',
                '訂單成立',
                '服務中',
                '訂單完成',
                '訂單取消'
            )
        ),
    CONSTRAINT chk_order_lifecycle_state_event_after_status
        CHECK (
            after_status IN (
                '洽談中',
                '訂單成立',
                '服務中',
                '訂單完成',
                '訂單取消'
            )
        ),
    CONSTRAINT chk_order_lifecycle_state_event_required_text
        CHECK (
            CHAR_LENGTH(TRIM(trigger_event)) > 0
            AND CHAR_LENGTH(TRIM(actor)) > 0
            AND CHAR_LENGTH(TRIM(idempotency_key)) > 0
        ),
    CONSTRAINT chk_order_lifecycle_state_event_facts_snapshot
        CHECK (JSON_TYPE(facts_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_order_lifecycle_state_events_before_update;
CREATE TRIGGER trg_order_lifecycle_state_events_before_update
BEFORE UPDATE ON order_lifecycle_state_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_order_lifecycle_state_events_before_delete;
CREATE TRIGGER trg_order_lifecycle_state_events_before_delete
BEFORE DELETE ON order_lifecycle_state_events
FOR EACH ROW
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be deleted';

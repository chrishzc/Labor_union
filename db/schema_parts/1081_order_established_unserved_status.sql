-- Append zero-service terminal status while preserving enum ordinals and every business row.
ALTER TABLE orders
    MODIFY COLUMN `status` enum('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消','歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成','成立後未服務') NOT NULL DEFAULT '洽談中';

ALTER TABLE order_terms_apply_receipts
    MODIFY COLUMN `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消','歷史訂單－服務完成','歷史訂單－帳務完成','待補件','歷史訂單－未服務','歷史訂單－服務中','成立後未服務') NOT NULL;

ALTER TABLE order_cancellation_apply_receipts
    MODIFY COLUMN `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消','成立後未服務') NOT NULL;

ALTER TABLE order_lifecycle_state_events
    DROP CHECK chk_order_lifecycle_state_event_before_status,
    DROP CHECK chk_order_lifecycle_state_event_after_status,
    ADD CONSTRAINT chk_order_lifecycle_state_event_before_status CHECK (
        before_status IN ('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消','歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成','成立後未服務')
    ),
    ADD CONSTRAINT chk_order_lifecycle_state_event_after_status CHECK (
        after_status IN ('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消','歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成','成立後未服務')
    );

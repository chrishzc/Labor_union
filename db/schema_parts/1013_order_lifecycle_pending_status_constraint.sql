-- File: 1013_order_lifecycle_pending_status_constraint.sql
-- Description: 讓 lifecycle event 如實保存既有待補件 Orders 的 before／after status。

ALTER TABLE order_lifecycle_state_events
    DROP CHECK chk_order_lifecycle_state_event_before_status,
    ADD CONSTRAINT chk_order_lifecycle_state_event_before_status
        CHECK (
            before_status IN (
                '待補件',
                '洽談中',
                '訂單成立',
                '服務中',
                '訂單完成',
                '訂單取消'
            )
        );

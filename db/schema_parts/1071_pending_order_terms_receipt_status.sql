-- Append the pending-completion status without changing existing receipt ordinals.
ALTER TABLE order_terms_apply_receipts
    MODIFY COLUMN lifecycle_status ENUM(
        '洽談中','訂單成立','服務中','訂單完成','訂單取消',
        '歷史訂單－服務完成','歷史訂單－帳務完成','待補件'
    ) NOT NULL;

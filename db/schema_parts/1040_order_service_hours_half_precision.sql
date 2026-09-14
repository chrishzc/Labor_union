ALTER TABLE orders
    MODIFY COLUMN service_hours_per_day DECIMAL(4, 1) DEFAULT 0.0
        COMMENT '每日服務時數 (J)，以 0.5 小時為單位',
    ADD CONSTRAINT chk_orders_service_hours_half_hour CHECK (
        service_hours_per_day >= 0 AND service_hours_per_day <= 24
        AND MOD(service_hours_per_day * 2, 1) = 0
    );

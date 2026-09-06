module: service-date-confirmation
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/service-date-confirmation.md
layout_status: custom_current

# Owned verification
- `orders_service_dates_flow.test.tsx` — OrdersPage service-date confirmation flow；保護 server precision、排休覆寫、唯一確認服務日期、Preview／Confirm／Apply、manual-date fallback 與 workspace applicability。

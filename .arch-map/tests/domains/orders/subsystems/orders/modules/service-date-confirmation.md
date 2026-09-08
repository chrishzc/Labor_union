module: service-date-confirmation
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/service-date-confirmation.md
layout_status: custom_current

# Owned verification
- `order_workbench_v2_service_dates.test.tsx` — Order Workbench V2 service-date confirmation flow；保護 server precision、案件一致性、Preview／Confirm／Apply、正式回讀與失敗時 fail closed。

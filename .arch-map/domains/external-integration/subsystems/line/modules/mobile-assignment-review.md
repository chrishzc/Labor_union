# Module: mobile-assignment-review

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供工會人員 target-isolated mobile work surfaces：待辦工作台分組呈現 Client Profile pending 資料異動、
LINE Identity pending 重綁／身分異常與 Scheduling pending 請假待辦，並提供 Matching／Scheduling
媒合與排班案件工具入口；客服中心沿用 Customer Service workflow，異常中心只讀 current `LINE-006`，
營運摘要只讀 current business week `operations-report.v3`。待辦項目與數量只來自各 owner 的 bounded
Query；沒有 pending Query 的案件工具不計數。四個工會管理入口均以role-scoped LINE current fact與
同一 actor 的persisted-human Session驗證，owner查詢與操作再驗證所需capability；Scheduling案件工具薄轉接既有Assignment Plan
Query／Preview／Apply／readback。此 Module 不建立mobile business state、跨owner approval root或writer。
缺Admin Session時只導向既有React password／MFA登入，使用closed target return identity回到同一mobile
route；LINE binding不簽發或傳遞Admin token。

## Implementation
- `api/routes/line_mobile_admin.py`
- `api/dependencies/line_identity.py`
- `line/static/mobile_admin.html`
- `line/static/identity.html`
- `line/static/gateway.html`

## Dependencies
- outbound: `customer-service` — existing ticket Query／reply workflow only.
- outbound: `clients/client-profile` — existing pending request Query與owner Preview／Apply；mobile只作presentation。
- outbound: `scheduling/leave-substitution` — existing pending leave inbox／受理入口；正式代班仍走owner Preview／Apply。
- outbound: `scheduling/matching-coordination` — existing案件型Query／Preview／Apply；無pending Query時不顯示數量。
- outbound: `anomalies/anomalies` — current-only `LINE-006` bounded Query.
- outbound: `global/reporting` — current business week `operations-report.v3` Query projected to six summary counts.
- outbound: `scheduling/scheduling` — existing Assignment Plan workflow; mobile adapter does not own Scheduling state.

## Verification
- layout_status: `custom_current`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_legacy_static_surfaces.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_assignment_review_entrypoint.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_review_pagination.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_work_surfaces.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_static_mutation_ui.py`

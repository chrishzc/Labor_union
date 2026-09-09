# Module: mobile-assignment-review

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供工會人員 target-isolated mobile work surfaces：待辦工作台只呈現 pending 月嫂身分驗證，客服中心沿用
Customer Service workflow，異常中心只讀 current `LINE-006`，營運摘要只讀 current business week
`operations-report.v3`。以role-scoped LINE current fact驗證mobile actor；Scheduling案件工具另以
persisted-human Session/capability薄轉接既有Assignment Plan Query／Preview／Apply／readback。此 Module
不建立mobile business state、跨owner待辦aggregate、approval root或writer。
缺Admin Session時只導向既有React password／MFA登入，使用closed `scheduling_review` return identity回到同一
mobile route；LINE binding不簽發或傳遞Admin token。

## Implementation
- `api/routes/line_mobile_admin.py`
- `api/dependencies/line_identity.py`
- `line/static/mobile_admin.html`
- `line/static/identity.html`
- `line/static/gateway.html`

## Dependencies
- outbound: `customer-service` — existing ticket Query／reply workflow only.
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

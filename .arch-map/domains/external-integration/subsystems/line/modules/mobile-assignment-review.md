# Module: mobile-assignment-review

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供工會人員 target-isolated mobile work surfaces：待辦工作台分組呈現 Client Profile pending 資料異動、
LINE Identity pending 重綁／身分異常與 Scheduling pending 請假待辦，並提供 Matching／Scheduling
媒合人工跟進待辦與排班案件工具入口；客服中心沿用 Customer Service workflow，狀態追蹤以 Orders 十三核心階段唯讀顯示未完成訂單、下一步與月嫂願意後的正式媒合提示，
營運摘要只讀 current business week `operations-report.v3`。舊 `anomalies_center` target 僅相容導向狀態追蹤；待辦項目與數量只來自各 owner 的 bounded
Query；Matching 人工跟進只投影「非空已聯繫池全員終結、零願意、零調整條件」，初次搜尋零候選不計數。四個工會管理入口均以server-verified LINE token、
role-scoped LINE current fact與enabled Admin owner驗證，owner查詢與操作再驗證所需capability；Scheduling案件工具薄轉接既有Assignment Plan
Query／Preview／Apply／readback。此 Module 不建立mobile business state、跨owner approval root或writer。
LINE binding不簽發或傳遞一般後台Admin Session，LIFF也不導向React password／MFA登入。

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
- outbound: `scheduling/matching-coordination` — 衍生的人工跟進 bounded Query 與 existing 案件型 Query／Preview／Apply；mobile 只顯示 current task 與群組通知狀態，不建立 Matching root。
- outbound: `orders/order-summary` — bounded unfinished Order case options only；mobile不推算可編輯狀態。
- outbound: `orders/operational-stage-projection` — 未完成訂單十三核心階段、最後更新與下一步的 bounded read-only Query；候選意願由 Scheduling typed pool Query 補充，不由 mobile 前端推算。
- legacy outbound: `anomalies/anomalies` — endpoint 暫保留相容，但 Rich Menu／LIFF current surface 不再查詢或顯示 `LINE-006`。
- outbound: `global/reporting` — current business week `operations-report.v3` Query projected to six summary counts.
- outbound: `scheduling/scheduling` — existing Assignment Plan workflow，加上 active Staff 與 confirmed service-date options；mobile adapter does not own Scheduling state.

## Verification
- layout_status: `custom_current`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_legacy_static_surfaces.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_assignment_review_entrypoint.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_review_pagination.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_work_surfaces.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_static_mutation_ui.py`

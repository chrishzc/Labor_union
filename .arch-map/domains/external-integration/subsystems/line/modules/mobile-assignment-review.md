# Module: mobile-assignment-review

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供工會人員 target-isolated mobile work surfaces：待辦工作台分組呈現 Client Profile pending 資料異動、
LINE Identity pending 重綁／身分異常與 Scheduling pending 請假待辦，並提供 Matching／Scheduling
月嫂確認／條件協調、24 小時月嫂回覆提醒、客戶推薦聯絡／簽約／7 天內部提醒及排班案件工具入口；客服中心沿用 Customer Service workflow，狀態追蹤以 Orders 十三核心階段唯讀顯示未完成訂單、下一步與月嫂願意後的正式媒合提示，
營運摘要只讀 current business week `operations-report.v3`。舊 `anomalies_center` target 僅相容導向狀態追蹤；待辦項目與數量只來自各 owner 的 bounded
Query；確認與條件協調由事件衍生待辦，24 小時只作未回覆提醒，不關閉回覆或發群組通知；初次搜尋零候選不計數。四個工會管理入口均以server-verified LINE token、
role-scoped LINE current fact與enabled Admin owner驗證，owner查詢與操作再驗證所需capability；Scheduling案件工具薄轉接既有Assignment Plan
Query／Preview／Apply／readback。此 Module 不建立mobile business state、跨owner approval root或writer。
LINE binding不簽發或傳遞一般後台Admin Session，LIFF也不導向React password／MFA登入。

## Implementation
- `api/routes/line_mobile_admin.py`
- pending leave pagination: `/staff-leave-requests/page` 經 Scheduling 原查詢提供 pending／accepted_for_processing 完整總數與分頁；原單狀態清單入口保留。客戶資料異動、月嫂確認／協調、推薦／簽約與回覆提醒均使用 owner 分頁及完整總數；已處理後重新讀取，不以本機扣數。
- `api/dependencies/line_identity.py`
- `line/static/mobile_admin.html`
- `line/static/identity.html`
- `line/static/gateway.html`
- deposit payment tasks: `api/routes/line_deposit_payment.py`，見同層 `deposit-notifications.md`；工會人員 Query／Send，缺繳費資訊或客戶 LINE 綁定時保留人工待辦。
- paid uncreated group tasks: `/order-group-todos`，只列正式已核銷、正常未結案且尚無群組綁定案件；Query 規則與測試歸同層 `order-group-coordination.md`，mobile 只提供複製綁定指令。

## Dependencies
- outbound: `customer-service` — existing ticket Query／reply workflow only.
- outbound: `clients/client-profile` — existing pending request Query與owner Preview／Apply；mobile只作presentation。
- outbound: `scheduling/leave-substitution` — existing pending leave inbox／受理入口；正式代班仍走owner Preview／Apply。
- outbound: `scheduling/matching-coordination` — 確認／條件協調 Query 與人員文案 Send；客戶提供更新後條件，人員可再次詢問或一鍵審核通過。改單由協調 application 在單一 outer UoW 借用既有 Orders writer，之後才可選擇月嫂重新詢問。有效工會人員及 matching capability 即可操作，不限定 system_admin；另以 `/customer-recommendation-followups` 唯讀呈現推薦聯絡、簽約與 7 天待辦，留言操作重用原客服介面；mobile 不建立 Matching root。
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

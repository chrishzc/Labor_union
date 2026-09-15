# Subsystem: line

## Parent
- domain: `external-integration`

## Responsibility
處理 LINE webhook、identity binding/review、LIFF/self-service transport、rich menu／message delivery與committed delivery worker composition；擁有 identity root／owner projections／current-fact interpretation，business mutation回owning Subsystem。

## Modules
- `worker-runtime-monitoring` — canonical worker cycle orchestration、success／failure heartbeat 與 runtime health classification；path: `modules/worker-runtime-monitoring.md`
- `delivery-provider-transport` — committed delivery task 共用的 provider outcome contract 與 LINE Messaging API transport adapter；path: `modules/delivery-provider-transport.md`
- `delivery-task-presentation` — LINE delivery task查詢工作台的business-facing presentation；path: `modules/delivery-task-presentation.md`
- `line-identity-management` — canonical LINE identity binding and review persistence; path: `modules/line-identity-management.md`
- `line-identity-maintenance-presentation` — LINE identity更正與解除維護的business-facing presentation；path: `modules/line-identity-maintenance-presentation.md`
- `line-identity-review-presentation` — LINE identity人工審核工作台的business-facing presentation；path: `modules/line-identity-review-presentation.md`
- `registration-presentation` — LIFF 客戶需求調查表單的呈現與本地輸入驗證；path: `modules/registration-presentation.md`
- `notification-rules-presentation` — LINE通知規則維護的business-facing presentation；path: `modules/notification-rules-presentation.md`
- `notification-failure-current-fact` — LINE-006 typed zero-write group readback、manual replay lineage與bounded recheck；path: `modules/notification-failure-current-fact.md`
- `notification-baseline-bootstrap` — Task96 M1–M4 versioned notification catalog與development-only source fixture producer；path: `modules/notification-baseline-bootstrap.md`
- `order-pre-start-notification-source` — 服務開始前三日首期款提醒與第二期款到期提醒的唯讀候選掃描、immutable source-event投影及worker UoW；path: `modules/order-pre-start-notification-source.md`
- `test-fixture-bootstrap` — development-only LINE 身分、訂單情境與 Rich Menu 測試前置資料；path: `modules/test-fixture-bootstrap.md`
- `feedback` — M2 immutable LINE feedback root／receipt／aggregate與Customer Service ticket linkage；path: `modules/feedback.md`
- `complaint-ingress` — M4 canonical complaint normalization、Customer Service hold／HIGH escalation、masked empathy、告警與客戶結案通知的分離投遞；path: `modules/complaint-ingress.md`
- `customer-order-change-intake` — verified LIFF 客戶訂單異動 Query／Preview／Apply，Apply 只建立 Customer Service 人工確認需求；path: `modules/customer-order-change-intake.md`
- `matching-coordination-delivery` — M3 committed owner-intent至既有 LINE delivery task 的 typed projection與LINE-006 readback；path: `modules/matching-coordination-delivery.md`
- `order-group-coordination` — 已驗證管理員的 LINE 訂單群組綁定、參與者同步與邀請投遞；path: `modules/order-group-coordination.md`
- `mobile-assignment-review` — persisted-human、target-isolated mobile transport，轉接既有 Scheduling Assignment Plan Q/P/A/readback；path: `modules/mobile-assignment-review.md`
- `safe-review-link` — 短效一次性review-link transport、runtime owner 版本重驗、masked readback、receipt與committed local intent；不執行provider send；path: `modules/safe-review-link.md`
- `staff-order-view` — 已驗證月嫂查看自己有效指派的訂單摘要與可選篩選；path: `modules/staff-order-view.md`
- `staff-service-day-media` — 已驗證月嫂餐食照片 controlled-file staging；path: `modules/staff-service-day-media.md`
- `staff-payout-view` — 已驗證月嫂依本人綁定與目標付款月份查詢逐案薪資明細；path: `modules/staff-payout-view.md`
- `rich-menu-management` — Rich Menu typed draft editing, publication preparation and role-scoped management presentation; path: `modules/rich-menu-management.md`

## Dependencies
- outbound: `scheduling | case-import | orders | other owning domains` — typed commands only。
- outbound: external LINE provider — only after committed durable intent/outbox when side effect is required。
- inbound: `anomalies` — 只透過typed LINE-006 notification-failure current-fact readback讀取owner facts；LINE identity replacement由LINE Identity正常流程擁有，不形成LINE-004 anomaly；不授權Anomalies修正root或重算Delivery。

## Contracts
- `subsystems/line/` — LINE application workflows
- `subsystems/line/identity_management_contracts.py` — LINE Identity typed zero-write current-fact contract與合法雙角色 interpretation；不形成LINE-004 anomaly
- `infrastructure/mysql/line_identity_management_repository.py::current_fact` — root及owner projections唯一typed readback adapter
- `subsystems/line/notification_failure_current_fact.py`與`infrastructure/mysql/line_notification_repository.py::current_failure_fact` — LINE-006 group typed readback；無aggregate persistence。
- `api/routes/line_identity_management.py::GET /api/v1/line/identity-bindings/{line_user_id}/current-fact` — reader-protected current-fact entry；external caller evidence仍deferred
- `line/` — LINE transport/provider adapter root
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — integration、delivery、runtime target與safe-review-link邊界。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — self-service contract
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — identity contract
- `document/架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md` — required direct-flow acceptance；source存在或局部測試通過不取代流程驗收。

### 同群告警重新綁定（2026-09-13 使用者明確指示）

既有 owner `subsystems/line/runtime_alert_target_application.py::register_group` 承接
`order_group_application.py` 中已驗證管理員送出的「設定異常通知群組」。正式 reset 保留
歷史並停用 target；其後同群的新指令可重新啟用原 row，保留 target id／minimum_status，
並保存前後 state／version 的 receipt及audit。此變更不授權清除歷史或自動取代另一啟用群組。

同群已 active 時不重做 target mutation；已處理的舊 event 重播只回既有 receipt，不把
後來停用的群組復活。另一群 active 或多群 active 時拒絕；沿用 advisory lock、caller UoW、
既有 receipt／audit，不新增 writer。管理入口仍為 `api/routes/runtime_health.py` 的
`/api/v1/runtime/line-alert-targets`，reset及enable／disable仍走各自Preview／Apply。

### 投遞與好友事件的既有修正

`delivery_worker.py` 每次只 claim 即將處理的一筆，保留每輪預設25筆上限；送出前確認
同一未過期lease及取消狀態。Reply 5xx不確定結果不得立即Push，亦不自動重試該不確定回答。

`infrastructure/mysql/line_platform_identity_repository.py`保存晚到的好友事件與版本紀錄，
同一 adapter 內的 canonical 狀態與 legacy `line_users` 投影都不倒退；
`webhook_identity_handlers.py`的舊follow不新建歡迎訊息／flow，舊unfollow不取消目前通知，
一般message仍處理。文字「未解決」建單失敗須傳回consumer rollback／retry，不能排入
成功通報；這不改變Feedback owner的root／receipt契約。

## Verification routing
layout_status: `custom_current`

- default_boundary: Subsystem
- test_root: `tests/domains/external-integration/subsystems/line/`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/`.
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mysql_repositories.py`
- integration_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_application_contracts.py`
- integration_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_runtime_stage3.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_liff_entrypoint.py`
- integration_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_identity_stage4.py`
- integration_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_registration_atomicity.py`
- integration_root: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/`
- higher_boundary: LINE Identity first-release living baseline由Global schema/release routing分類；Anomalies consumer保留在其canonical integration root。
- regression: `tests/domains/external-integration/subsystems/line/subsystems/test_line_delivery_friend_regressions.py`
- regression: `tests/domains/external-integration/subsystems/line/subsystems/test_line_friend_feedback_regressions.py`
- regression: `tests/domains/external-integration/subsystems/line/subsystems/test_line_m4_continuation_regressions.py`
- integration_root: `ui_react/src/tests/line_successor_clients.test.ts`

上述修正的source基準為PR #299 `4eb58e07e94660308ba8afd05d39931f0301fdf1`；記錄中的
53項回歸只涵蓋指定情境，非全M1～M4通過。main合併、部署、實際DB與手機／provider狀態
須分別核對；本索引不把尚缺的請假客戶決策或告警到一次性review link證據標為superseded／passed。

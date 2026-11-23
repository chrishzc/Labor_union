# Module: mobile-assignment-review

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供工會人員 target-isolated mobile work surfaces：待辦工作台分組呈現 LINE Identity pending 重綁／身分異常與 Scheduling 服務中換人需求，並提供 Matching／Scheduling
24 小時月嫂回覆提醒、客戶推薦回覆／簽約／7 天內部提醒及排班案件工具入口。狀態追蹤以 Orders 十三核心階段唯讀顯示未完成訂單、下一步與月嫂願意後的正式媒合提示，
營運摘要只讀 current business week `operations-report.v3`。舊 `anomalies_center` target 導向狀態追蹤，舊 `customer_service` target 導向待辦工作台。待辦項目與數量只來自各 owner 的 bounded
Query；24 小時只作未回覆提醒，不關閉回覆或發群組通知；初次搜尋零候選不計數。四個工會管理入口均以server-verified LINE token、
role-scoped LINE current fact與enabled Admin owner驗證，owner查詢與操作再驗證所需capability；Scheduling案件工具薄轉接既有Assignment Plan
Query／Preview／Apply／readback。此 Module 不建立mobile business state、跨owner approval root或writer。
LINE binding不簽發或傳遞一般後台Admin Session，LIFF也不導向React password／MFA登入。

## Implementation
- Binding reminder sources `customer_binding` / `staff_binding` reuse LINE Identity's bounded owner query and binding-read capability. Desktop and mobile expose manual telephone/copy actions only; no new notification state or outbound task.
- `api/routes/notification_tasks.py`、`api/schemas/notification_tasks.py` — 桌面與 LIFF 共用逐來源唯讀 projection、allowlisted catalog 及 bounded cursor；每次請求只讀原 owner，不新增 inbox／read state。來源失敗明示，來源原分頁保留；搜尋明示只限已載入事項。舊 `customer_service` 查詢回 410，推薦待辦使用配對方案與跟進狀態組成的識別碼。
- 月嫂資料異動只列於桌面「通知事項」，唯讀查詢 Staff 申請的 Redis 待審摘要，從單筆連結開啟月嫂名冊審核；不建立 LINE 寄送工作。
- `import_fields` 只列於桌面「通知事項」，以 `data_browser.read` 查詢 Case Import 的 bounded current field issues。每案一筆，逐欄連到客戶名冊的正式修正入口，讀回後依目前問題更新。
- `api/routes/notification_task_actions.py` — session／LINE capability 薄轉接原訂金、登記與 delivery command；runtime/query 改為 authenticated 唯讀系統摘要，舊 target command 由原 owner 回退役錯誤；原 owner 擁有 fresh check、冪等、receipt 及 outer commit。LIFF 不接受桌面 Session。
- `ui_react/src/pages/NotificationTasksPreviewPage.tsx`、`ui_react/src/pages/NotificationTasksPreviewPage.css`、`ui_react/src/api/line_notifications/notification_tasks_client.ts` — 正式通知事項查詢、來源分頁、同案工作區入口及缺綁定修復入口；沒有範例資料 fallback。
- `ui_react/src/components/NotificationTaskActions.tsx` — 桌面通知僅提供正式作業深連結與客戶／月嫂綁定、人工建群三類指引。`source_observed`：服務登記、資料異動、服務中換人、寄送異常、通知建立異常仍有 owning 工作面連結，攜帶單筆 identity；不在通知頁重複操作。推薦待辦連到本案推薦或簽約工作區。
- `ui_react/src/components/TaskOperation.css` — 通知人工指引與正式作業面沿用相同按鈕／表單樣式，無流程邏輯。
- `ui_react/src/components/RegistrationApplications.tsx` — notification initial ID 與原核准後 readback callback。
- `ui_react/src/components/LineIdentityWorkbench.tsx` — notification review deep link 讀取同一審核申請。
- `ui_react/src/components/OrderWorkbenchV2Drawer.tsx` — notification `work=matching|recommendation|contracts|service|intake` 僅選擇現有工作區。
- `api/routes/line_mobile_admin.py`
- `api/routes/line_mobile_staff_leave_coordination.py` — 舊客戶同意順延入口回 410。共用 `service_start` 待辦只查服務中換人，沿 Scheduling owner 的同一分頁及完整總數。
- 請假 source 與受理／退回入口回 410，不列共用待辦；歷史列表／readback 保留。推薦／簽約與回覆提醒均使用 owner 分頁及完整總數；已處理後重新讀取，不以本機扣數。
- `api/dependencies/line_identity.py`
- `line/static/mobile_admin.html` — staff_review 最上方提供可展開系統狀態卡及手動刷新；只讀既有 runtime/query，不顯示通知對象設定，查詢錯誤不阻塞待辦。
- `line/static/identity.html`
- `line/static/gateway.html`
- deposit payment tasks: `api/routes/line_deposit_payment.py`，見同層 `deposit-notifications.md`；工會人員 Query／Send，缺繳費資訊或客戶 LINE 綁定時保留人工待辦。
- payment overdue / log reminder tasks: `/payment-overdue-reminders[/send]`、`/log-reminders[/send]` 薄轉接既有 owner Query／Send，保留分頁、完整總數、capability、fresh check、同操作識別與寄送工作狀態；查詢不排送。
- paid uncreated group tasks: `/order-group-todos`，只列正式已核銷、正常未結案且尚無群組綁定案件；Query 規則與測試歸同層 `order-group-coordination.md`，mobile 只提供複製綁定指令。

通知中心 `payment_receipt` 來源只投影 LINE 入帳通知 owner 的已核銷待辦；桌面按「前往帳務確認」攜帶案號、期別及 settlement identity，帳務才可人員 Send。手機僅提供帳務處理指引與案號複製，不引導跨 Session 或直接寄送。訂金舊來源只列未核銷提醒，避免已核銷項目重複列入。

## Dependencies
- outbound: `scheduling/leave-substitution` — 服務中換人需求沿其原案件流程，請假記錄保留歷史 Query；開工與延期衝突的管理員調班不列代班待辦。
- outbound: `scheduling/matching-coordination` — 以 `/matching-followups` 唯讀呈現 24 小時月嫂未回覆提醒，以 `/customer-recommendation-followups` 唯讀呈現推薦回覆待處理、待簽約與實際送達後 7 天待跟進。
- outbound: `orders/order-summary` — bounded unfinished Order case options only；mobile不推算可編輯狀態。
- outbound: `orders/operational-stage-projection` — 未完成訂單十三核心階段、最後更新與下一步的 bounded read-only Query；候選意願由 Scheduling typed pool Query 補充，不由 mobile 前端推算。
- outbound: `anomalies/anomalies` — notification_failure source 重用 LINE-006 bounded current projection 與 LINE Notification fresh predicate；只讀、原 keyset cursor、原補送 writer，不恢復退役 anomalies_center target。
- outbound: `global/reporting` — current business week `operations-report.v3` Query projected to six summary counts.
- outbound: `scheduling/scheduling` — existing Assignment Plan workflow，加上 active Staff 與 confirmed service-date options；mobile adapter does not own Scheduling state.
- outbound: `subsystems/line/payment_overdue_reminders.py`、`subsystems/line/service_day_log_reminders.py` — 各期金額／對象與連續缺漏由既有 application 擁有；mobile 不另算日期、餘額或寄送資格。

- 桌面正式作業提交後回讀原 owner；返回通知頁重查來源與寄送紀錄。手機跟進清單由原 owner 唯讀提供。

- LIFF 事項以 identity 聚焦；identity 單筆 Query 薄轉接原 owner，deposit 以 case_no 與核銷狀態篩選。其他來源只顯示重查後同 identity 卡片。
- 開啟事項與返回共用既有查詢序號，晚到回應忽略；跟進提供手機狀態追蹤與案號複製。

- 建立前通知阻擋沿既有 LINE-006／Notification owner；兩端同列 source、去重確切 task identity，原 manual replay 薄轉接及資格預覽。手機管理操作一次點擊內部 Preview／Apply，細部回應亦依事項／generation 忽略晚到結果。

## Contracts
- `architecture_declared`：`.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md` §2、§5.1.1 與 §5.2 規定客服工單待辦退役、留言由 LINE 官方帳號處理，舊手機入口導向待辦工作台。舊 Query 與歷史保留依 `19_Global_Entry_Point_Governance.md` §3.2。
- `architecture_declared`：`.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md` §5.1.1 的 `service_start` 來源只呈現服務中換人需求。開工、延期衝突與局部代班不列通知待辦及總數，入口退役依 `19_Global_Entry_Point_Governance.md`。

## Verification
- integration_root: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/notification_tasks_sync.test.tsx` — 既有模擬案例確認回到通知頁會重新查詢推薦待辦；來源回傳零筆時移除先前項目。
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_notification_workbench.py`
- integration_root: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/notification_tasks_page.test.tsx`
- integration_root: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/notification_destinations.test.tsx`
- layout_status: `custom_current`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_legacy_static_surfaces.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_assignment_review_entrypoint.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_review_pagination.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_work_surfaces.py`
- higher_boundary: `tests/domains/external-integration/subsystems/line/integration/test_line_static_mutation_ui.py` — 上位 LINE Subsystem 的身分、客服與手機操作跨 owner 靜態契約。

2026-10-30：runtime 不再列為逐來源待辦或通知對象設定；系統狀態由 `worker-runtime-monitoring` 的 RuntimeStatusQuery 擁有，mobile adapter 先驗 LINE token／enabled current Admin／MONITOR_READ，再輸出去敏封閉 view。

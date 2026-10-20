# Module: matching-schedule-confirmation

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
將 current confirmed-service-date version 與 formal matching plan 投影為客戶／月嫂 recipient snapshots，編排 durable LINE delivery intent，並以 recipient-bound confirmation event 與 fresh Query readback 保護正式排班 gate。

## Implementation
- primary:
  - `domains/scheduling/commitment_execution.py` — 首次轉換的簽約人員／服務量與 current 已確認日期核對。
  - `subsystems/scheduling/matching_schedule_confirmation.py`
  - `subsystems/scheduling/automatic_service_arrangement.py` — current recipient confirmation／owner Preview → existing durable assignment command；Query zero-write。
  - `infrastructure/mysql/automatic_service_arrangement_repository.py`
  - `api/dependencies/service_arrangement_automation.py`
  - `subsystems/scheduling/assignment_plan_workflow.py`
  - `subsystems/scheduling/assignment_plan_impacts.py`
  - `infrastructure/mysql/assignment_plan_impact_ports.py` — Client Finance／Payroll／Orders typed impact 與同一 outer transaction 的持久化配接。
  - `infrastructure/mysql/matching_schedule_confirmation_repository.py`
  - `infrastructure/mysql/assignment_plan_repository.py` — fresh-lock actual occupancy；buffer 不構成 hard facts。
- entrypoints:
  - `api/routes/matching_schedule_confirmation.py`
  - `api/routes/assignment_plan.py`
  - `ui_react/src/api/scheduling/matching_schedule_confirmation_client.ts`
  - `ui_react/src/api/scheduling/assignment_plan_mutation_client.ts` — canonical Apply／closed job outcome transport。
  - `ui_react/src/api/scheduling/service_arrangement_status_client.ts` — strict automatic arrangement status and completion status transport。
  - `ui_react/src/components/MatchingScheduleAndAssignmentActions.tsx`
  - `ui_react/src/components/OrderAssignmentPlanPanel.tsx`
- inbound LINE adaptation:
  - `subsystems/line/matching_postback_application.py`

## Boundaries
- Assignment Plan Query 僅讀 current Orders／Scheduling 與 nullable 已存在的 Finance／Payroll 版本；缺根或時數不阻擋唯讀，Preview／Apply 保留完整正式驗證。
  - `infrastructure/mysql/order_terms_read_model.py` 的 `select_current_assignments` 共用於 Assignment Plan Query 與付款查核；最新採納的歷史 assignment 無 generation 時仍回傳同一 identity。唯讀 Query 使用 `AssignmentPlanQueryAssignment`，不把 mutation 的逐日日期條件當成查閱資格。

- 推薦與排班介面呈現自動等待訂金鎖及已轉正式班表狀態，不要求使用者手動 acquire；保留正式換人／日期調整入口及既有排班條件驗證。
- 自動排班 discovery 以 active plan／current 日期版本掃描，不依賴日期表 snapshot 已建立；dispatch 在獨立原 UoW 借用 canonical 等待鎖 writer，銜接升級前已確認但從未保留的案件。Query 仍零寫入，明確釋放／已轉換的鎖不自行恢復；衝突維持 awaiting_conditions，不 enqueue 排班。
- 初次正式排班以完整服務日期與 Client Finance 衍生應付套用 Payroll 付款日政策；同一 outer Apply 由 Orders 保存唯一既定應付日、Payroll 保存相同 obligation due date。後續改期保留既定應付日，不等完工才形成日期。
- 單一月嫂於正式指派前的日期表、檔期保留與自動排班以 current confirmed dates 銜接實際開始日，不與舊推薦期間取空交集；Assignment gate 核對 immutable child dates、staff 與實際開始日。Query 不將舊 0 天 snapshot 的確認冒充新日期確認，人工稽核 metadata 不算日期漂移。
- 實際開始日變動不重簽：`domains/scheduling/commitment_execution.py` 保留 signed plan／staff／per-staff days，日期差異須精確對應 current 雙方確認 snapshot；conversion event 保存日期版本引用，不改寫原簽約歷史。
- Scheduling owns schedule snapshots, recipient confirmation facts and the assignment gate.
- LINE owns verified user identity, interaction transport, durable delivery task and provider outcome; the postback adapter only forwards a recipient-bound typed decision.
- Zero-pool and candidate-delivery semantics are outside this module's current Task 96 contract.
- `api/dependencies/private_operations.py` 接續 discovery，enqueue 與 canonical worker transactions 分開；所有 root writes 仍由既有 assignment Apply 擁有。

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`

## Verification
- test_root: `ui_react/src/tests/matching_schedule_confirmation_actions.test.tsx`
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-schedule-confirmation/`
- direct_api_test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-schedule-confirmation/`
- layout_status: `custom_current`
- higher-boundary integration:
  - `tests/domains/external-integration/subsystems/line/integration/test_matching_schedule_confirmation.py`
  - `tests/domains/external-integration/subsystems/line/subsystems/test_line_matching_postback_stage7.py`
- compatibility tests:
  - `tests/test_matching_schedule_confirmation_api_client.py`
  - `tests/test_matching_schedule_confirmation_panel.py`

## Provenance
- Owner and recipient-confirmation semantics: `architecture_declared` — Scheduling and LINE formal specs.
- Source, entrypoint and test paths: `source_observed` — current repository.

## Change triggers
Reconcile when schedule snapshot ownership, recipient binding, postback adaptation, delivery intent, assignment gate, API/client/UI entry or focused verification path changes.

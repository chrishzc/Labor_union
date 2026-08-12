# Assignments／Scheduling Domain

## 1. Domain 責任

擁有 waiting-deposit 檔期鎖、正式 assignment、assignment-owned 正式服務日、請假／順延／代班、月嫂占用、七日 buffer、排班 Preview／Apply，以及日期、工時和 assignment status 投影。

不擁有 Orders Terms／lifecycle／actual start、客戶帳務、月嫂應付、Alert workflow、LINE 或契約平台流程。

## 2. SSOT

| 事實 | 唯一權威 |
|---|---|
| assignment 歸屬與區段歷史 | `case_staff_assignments` 的版本化有效紀錄 |
| 每日正式服務 owner | effective `staff_schedule.assignment_id` |
| assignment 檔期占用 | 有效 assignment 的完整連續區間，包含排休與請假日 |
| actual hours | 正式服務日數 × Orders 每日服務時數 |
| assignment status | 第一／最後正式服務時刻與 Global Clock |
| leave／substitution lineage | batch header＋append-only 每日 outcome events |
| waiting-deposit lock | lock header、days 與 events |
| 七日 buffer | 獨立 buffer facts；不混入服務日或薪資 |
| 可接案結果 | 上述占用事實的 Query projection |
| 重建原因與 old/new lineage | 通用 assignment rebuild event |

`orders.staff_id`、`planned_hours`、`actual_hours_adjustments`、`replaced_assignment_id` 及 `original_assigned_*` 不得成為新架構依賴。

## 3. Domain invariants

- assignment／schedule 改動一律 Preview，Apply 時 cancel-old／create-new，不原地截短、換人或覆寫。
- cancelled assignment 保留歷史但完全排除目前投影。
- 同案同日只有一個正式服務 owner；不支援半日或分時交接。
- 全案有效正式服務量必須等於 Orders 契約服務量。
- 全案條款變更重建全部有效 assignments；局部請假／代班只重建受影響 family，但仍重驗全案。
- assignment 的整段連續區間都占用月嫂，休假不能被誤判為可接其他案件。
- 一般洽談不占檔期；客戶確認後才形成 waiting-deposit lock。
- 訂金逾期只形成異常，不自動釋放。
- 每個 assignment 預計結束日後七天為獨立 buffer；全案第一個正式服務開始時同交易解除全部 buffer。
- 國定假日不自動雙倍薪；只接受明確 special-pay event。
- 全部服務完成後不得取消訂單或縮減月嫂完整履約薪資。

## 4. Subsystems

### Availability Query

從 assignment interval、waiting lock、buffer 及其他案件占用推導可用日期。Staff holiday preference 只作排序，不是硬性淘汰；Query 不寫入。

### Matching Segment Plan

單一月嫂完整覆蓋優先，無法覆蓋才產生 2–4 個連續分段。草稿可顯示 gap／overlap，正式聯繫、鎖定與 Apply 前必須完整合法。

### Waiting Deposit Lock

只提供 Acquire、Release-to-unbound、Cancel、Convert。訂金有效性由 Client Finance typed port 提供。服務區間與 buffer 同時查衝突，每次轉移保存事件。

### Assignment Plan

提供 Query、Preview、Apply；支援 bootstrap、分段增減、換人、日期調整及 Orders Terms 全案重建。Apply 取消舊紀錄並新增新集合，通用 rebuild event 保存一對多／多對一 lineage。

第一個正式 assignment 的 bootstrap 必須轉換同案仍有效的 waiting-deposit lock；
若沒有 waiting lock，回 `assignment_plan_bootstrap.waiting_lock_required`，不得直接建立
正式 assignment。轉換前仍必須驗證契約流程完成、服務時間完整及訂金正式核銷；
legacy 缺漏只能進異常與人工修正，不得由 Assignment Plan 猜測或補造。

依第 `21` 份正式規格，存在簽約前 commitment 時，第一次 bootstrap 還必須鎖定並驗證
matching plan/version、staff 與精確日期集合完全相同；不同時回
`commitment_execution_mismatch` 且零寫入。成功時 assignments、schedules、Payroll impact、
commitment `converted` terminal event、outbox 與 receipt 同一交易提交。Calendar Read、Payroll
與 Government Subsidy 在 conversion 前不得讀取 commitment days。

### Schedule Projection

由 assignment segment、排休規則及正式 leave outcome 產生完整 assignment-owned 日曆。禁止單日 CRUD、獨立 Generate 或 UI 直接切換 `is_work_day`。

### Leave／Substitution

多日請假為一次 Preview、一個 fingerprint、一次 Apply transaction；每一天保存 immutable outcome。正式結果只允許順延或指定代班。代班建立獨立 assignment；取消或更正以反向／替代事件處理。

2026-08-12 人工裁決：月嫂請假審核的 API、typed client 與管理入口由 Scheduling 擁有，
不得掛在 LINE identity review route 或 `LineAdminApiClient`。LINE 只提供 verified identity、
delivery intent 與通知結果。現有依賴已退役 `services.*` 的 review service 是 `live-drift`，
在 canonical repository／outer UoW、capability、typed result 與 entrypoint replacement 完成前
不得掛入 FastAPI。

Batch replay：

- `batch_key` 是一次多日操作的冪等 identity，並綁定 canonical request snapshot、
  Preview fingerprint、actor 與 reason。
- Apply 先以 `batch_key FOR UPDATE` 讀取 header；不存在才可進入施工，存在時必須再鎖定
  並讀取全部 child events。
- header、item count、連續 ordinal、case／assignment linkage、request snapshot 與
  fingerprint 全部完全相同時回傳原 receipt，不再執行 mutation。
- 相同 `batch_key` 搭配不同 request 或 fingerprint 回 `batch_key_request_identity_conflict`；
  header 缺 child、ordinal 重複／缺號或 lineage 不一致屬資料完整性 blocker，不自動補寫。
- batch header、逐日 events、assignment／schedule replacement、payroll impacts、outbox
  與 receipt 必須同一 transaction；rollback 後不得留下可被誤認為成功的 partial batch。

### Assignment Lifecycle Projection

`planned`、`active`、`completed` 由正式服務時刻推導；中間休假仍 active。`cancelled` 只由命令產生；`replaced` 只作 legacy 相容。

### Calendar Read

逐日顯示 waiting lock、buffer、assignment interval、正式工作日與休假。只組合 typed ViewModel，不在 Query 或 render 時轉移狀態。

## 5. Modules

- `SegmentCoverageValidator`
- `AssignmentIntervalValidator`
- `OccupancyIntervalProjector`
- `OfficialWorkdayProjector`
- `ActualHoursCalculator`
- `CaseServiceConservationValidator`
- `AssignmentStatusProjector`
- `BufferDateProjector`
- `AvailabilityConflictDetector`
- `AssignmentRebuildPlanner`
- `ScheduleDiffBuilder`
- `LeaveResolutionPlanner`
- `SubstitutionOwnershipValidator`
- `SpecialPayProjector`
- `CandidateFingerprint`
- `RebuildLineageBuilder`

Modules 是純函式；不讀 DB、不取現在時間、不 import UI/API。

## 6. Apply transaction

```text
authorize／idempotency lookup
→ lock case aggregate/version
→ 依 preflight impacted set 按 staff_id 升冪鎖定月嫂占用
→ lock batch replay header／children
→ 載入 fresh Orders、Finance 與凍結事實
→ 使用 Preview modules 重建 candidate
→ 驗證 version／fingerprint／coverage／ownership／hours／occupancy
→ 取消受影響舊 assignments 與舊 current schedules
→ 新增 assignments、schedules、locks 與 immutable events
→ 推導 actual hours、status、actual end 及跨域 impacts
→ 委派 Orders lifecycle、Payroll、Client Finance
→ 寫 outbox／receipt
→ 單一 commit
```

對於涉及大量計算的排班指令（例如 `ApplyAssignmentPlan` 與 `ApplyLeaveSubstitutionBatch`），API 應支援回傳 `202 Accepted` 並以 Durable Job 於背景執行。背景 Worker 仍必須嚴格執行此處定義的「單一原子 transaction」，不得因為非同步執行而將 lock 與 commit 拆分為多次。

全 Scheduling commands 共用下列鎖定順序：

1. case／Scheduling aggregate；
2. 全部受影響 `staff` mutex rows，去重後按 `staff_id` 升冪；
3. replay batch header／children；
4. effective generation 與 assignments，按 assignment id 升冪；
5. schedules／waiting locks／buffer facts，按日期與 row id 穩定排序；
6. Payroll／Client Finance obligations，按 owning aggregate identity 穩定排序。

鎖 staff mutex 後必須 fresh 重建 impacted staff set。若 fresh facts 出現 preflight 未包含的
新 staff，不得中途再取得較小或任意順序的 mutex；本次 transaction rollback，回
`scheduling_lock_set_stale`，由呼叫端重新 Query／Preview。任何 repository／Subsystem
不得另訂第二套鎖順序或自行 commit。

鎖後必須重新驗證：Orders Terms／actual start／aggregate version、唯一 effective
generation、原 assignment 仍有效、所有目標 schedule 的日期與 owner、全案 coverage、
staff occupancy、waiting lock、七日 buffer、Payroll／Finance freeze、完成時刻及 Preview
fingerprint。任一不同均零 mutation 回 conflict；不得信任 Preview snapshot 或 UI payload。

## 7. 必要資料模型

- **已確認採用 `generation + effective` 模型**：每次正式 Apply 取消舊有效 generation、完整保留其 assignment／schedule 歷史，並建立新的 effective generation；目前排班、工時、檔期與薪資只讀 effective generation。
- 同一個 `case_no` 同一時間只能有一個 effective scheduling generation；切換 effective generation 必須與新 assignments、schedules、重建事件及 aggregate version 在同一交易完成。
- `UNIQUE(staff_id, work_date)` 與 `UNIQUE(case_no, assignment_sequence)` 必須納入 generation／effective 語意，使歷史 generation 與目前 generation 可共存，同時仍禁止 effective generation 內重複 ownership。
- 建立通用 rebuild command/event，保存 old/new sets、actor、reason、version、fingerprint 及 idempotency key。
- lock day 必須區分 `service` 與 `buffer`；buffer 有獨立 lifecycle。
- `staff_schedule.assignment_id` 必須進入 base schema，正式歷史不得 `ON DELETE CASCADE`。
- Scheduling aggregate 需要獨立 version 與 idempotency receipt。
- batch header 必須唯一 `batch_key`；child event 必須唯一
  `(batch_key, batch_item_index)` 與穩定 event identity，且 ordinals 從 0 連續。

## 8. 驗收

Module 驗證 coverage、full-interval occupancy、七日 buffer、時區、hours 與 fingerprint。
Subsystem 使用隔離 MySQL 驗證 Preview 零寫入、cancel/create、exact batch replay、
batch-key payload mismatch、partial replay corruption、鎖後 impacted-staff set 擴張、
相反 staff 順序的並行命令、stale、占用衝突及 rollback。Domain 覆蓋單／多月嫂、
waiting deposit、全案條款重建、局部請假、順延、代班、buffer 釋放與完整履約取消拒絕。

## 9. Typed Commands／Ports／Errors

Commands：

- `QueryStaffAvailability`
- `PreviewAssignmentPlan`
- `ApplyAssignmentPlan`
- `PreviewLeaveSubstitutionBatch`
- `ApplyLeaveSubstitutionBatch`
- `AcquireWaitingDepositLock`
- `ReleaseWaitingDepositLock`
- `ConvertWaitingDepositLock`
- `CancelWaitingDepositLock`
- `QueryCaseCalendar`

輸入 ports：

- `OrdersTermsFactsPort`
- `OrdersActualStartFactsPort`
- `ClientDepositSettlementFactsPort`
- `PayrollImpactCandidatePort`
- `ClientFinanceImpactCandidatePort`
- `BusinessClockPort`

Stable errors：

- `invalid_scheduling_intent`
- `case_not_found`
- `staff_not_found`
- `assignment_not_found`
- `coverage_incomplete`
- `service_ownership_conflict`
- `staff_occupancy_conflict`
- `waiting_lock_conflict`
- `buffer_conflict`
- `scheduling_generation_conflict`
- `scheduling_lock_set_stale`
- `stale_preview`
- `batch_key_request_identity_conflict`
- `invalid_batch_replay_snapshot`
- `scheduling_data_integrity_violation`
- `idempotency_conflict`
- `transaction_failed`

## 10. Live writer 退出

- `services/assignment_schedule_rest_date_service.py` 的 canonical batch replay、event 與純
  transition 可吸收；直接 UPDATE／DELETE assignment 或 schedule 的 mutation 必須移入
  Scheduling persistence adapter。
- `services/caregiver_availability_lock_*` 與 `services/caregiver_matching_*` 只可經 typed
  Waiting Lock／Assignment commands。
- `services/multi_caregiver_schedule_generation.py`、
  `services/multi_caregiver_schedule_adjustment_service.py`、
  `services/order_assignment_synchronization.py`、`services/payment_service.py` 與
  `services/db_service.py` 的 assignment／schedule writers 遷移後關閉。
- `services/actual_hours_adjustment_confirmation_service.py` 不得再寫權威 actual hours；
  legacy adjustment 僅供異常 recovery。
- final writer scan 必須證明 effective assignment、schedule、waiting lock、buffer、
  rebuild event 與 Scheduling version 都只有本 Domain persistence adapters 可寫。

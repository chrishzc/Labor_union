# Assignments／Scheduling Domain

## 1. Domain 責任

擁有 waiting-deposit 檔期鎖、正式 assignment、assignment-owned 正式服務日、請假／順延／代班、月嫂占用、七日 buffer、排班 Preview／Apply，以及日期、工時和 assignment status 投影。

不擁有 Orders Terms／lifecycle／actual start、客戶帳務、月嫂應付、Alert workflow、LINE 或契約平台流程。

## 2. SSOT

| 事實 | 唯一權威 |
|---|---|
| assignment 歸屬與區段歷史 | `case_staff_assignments` 的版本化有效紀錄 |
| 每日正式服務 owner | effective `staff_schedule.assignment_id` |
| completed assignment 的歷史區段 | `case_staff_assignments.status=completed` 與其正式起訖日 |
| assignment 檔期占用 | 有效 assignment 的完整連續區間，包含排休與請假日 |
| actual hours | 正式服務日數 × Orders 每日服務時數 |
| assignment status | 第一／最後正式服務時刻與 Global Clock |
| leave／substitution lineage | batch header＋append-only 每日 outcome events |
| waiting-deposit lock | lock header、days 與 events |
| 七日 buffer | 獨立 buffer facts；不混入服務日或薪資 |
| 可接案結果 | 上述占用事實的 Query projection |
| 長假／暫停接案 | versioned staff unavailability period 與 append-only cancel event |
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
- 每個尚未開始服務的 assignment 預計結束日後七天為獨立 buffer；全案第一個正式服務開始時同交易解除全部 buffer。Current Query 亦須以全案第一個正式服務時刻排除已開始／已完成案件的 stale active buffer root，不得讓 persistence marker 覆蓋 `planned／active／completed` lifecycle。
- 國定假日不自動雙倍薪；只接受明確 special-pay event。
- 全部服務完成後不得取消訂單或縮減月嫂完整履約薪資。

## 4. Subsystems

### Availability Query

從 assignment interval、waiting lock、buffer 及其他案件占用推導可用日期。Staff holiday preference 只作排序，不是硬性淘汰；Query 不寫入。

依第 `24` 份正式規格，Availability Query 亦讀取 current `long_leave`／
`temporarily_unavailable` 期間。與服務需求日期重疊時屬 actual conflict；七日 buffer 必須獨立回傳
`requires_manual_confirmation`，不得與不可服務期間或正式占用混成同一 hard block。不可服務期間
由 Scheduling 的 versioned Query 同時供 Matching 與 Calendar 使用。

### Matching Segment Plan

單一月嫂完整覆蓋優先，無法覆蓋才產生 2–4 個連續分段。草稿可顯示 gap／overlap，正式聯繫、鎖定與 Apply 前必須完整合法。

### Waiting Deposit Lock

只提供 Acquire、Release-to-unbound、Cancel、Convert。訂金有效性由 Client Finance typed port 提供。服務區間與 buffer 同時查衝突，每次轉移保存事件。
lock day 只對應該分段的正式服務日；固定週休不是 lock day。七日 buffer 是獨立衍生占用，
不得被 current projection 當成正式服務日，亦不得要求固定週休有 lock day。

### Assignment Plan

提供 Query、Preview、Apply；支援 bootstrap、分段增減、換人、日期調整及 Orders Terms 全案重建。Apply 取消舊紀錄並新增新集合，通用 rebuild event 保存一對多／多對一 lineage。

2026-08-27 人工裁決：服務前現任月嫂因車禍或其他正式不可服務事實必須
整案換人時，不是將 Orders／Scheduling version 改小，也不是原地改舊 assignment。
必須新增 version 更大的 caregiver-replacement event，supersede 舊 active matching／assignment
lineage，建立新 matching round，並讓 Orders 11 步投影回到最早失效的 caregiver-bound
step。整案重新媒合默認為 Step 2；只有 current replacement round 的 owner root 證明可沿用
合法候選池時，server 才可投影 Step 3／4。舊候選回覆、特定月嫂簽回、recipient
confirmation、waiting lock、commitment 與排班的 immutable 歷史保留，但不得滿足
新 round 的 gate。

分流根事實固定由 Scheduling 的 assignment-owned official service facts 決定：

- 尚未提供任何服務：可建立新 matching round 並讓 Orders current SOP 回 Step 2／3／4。
- 已提供任何服務：禁止整案回媒合，固定走既有 Leave／Substitution；只重建受影響
  assignment family，保留已服務日與原月嫂薪資事實，代班日由新 assignment 及既有
  Payroll impact 計算。不新建另一套代班或薪資公式。

第一個正式 assignment 的 bootstrap 必須轉換同案仍有效的 waiting-deposit lock；
若沒有 waiting lock，回 `assignment_plan_bootstrap.waiting_lock_required`，不得直接建立
正式 assignment。轉換前仍必須驗證契約流程完成、服務時間完整及訂金正式核銷；
legacy 缺漏只能進異常與人工修正，不得由 Assignment Plan 猜測或補造。

依第 `21` 份正式規格，存在簽約前 commitment 時，第一次 bootstrap 還必須鎖定並驗證
matching plan/version、staff 與精確日期集合完全相同；不同時回
`commitment_execution_mismatch` 且零寫入。成功時 assignments、schedules、Payroll impact、
commitment `converted` terminal event、outbox 與 receipt 同一交易提交。Calendar Read、Payroll
與 Government Subsidy 在 conversion 前不得讀取 commitment days。

#### Matching Schedule Confirmation Gate (2026-08-12)

Formal Assignment Plan Preview and Apply must fail closed unless a current schedule snapshot is
bound to the current Orders confirmed-service-date version. The customer must have confirmed the
parent schedule and every caregiver segment selected for formal conversion must have confirmed
its own child schedule from that same lineage. The gate blocks only formal assignment/scheduling;
candidate search, matching communication, willingness, and waiting-deposit lock remain available.
Any terms, confirmed-date, matching-plan, recipient-binding, or schedule-fingerprint change
invalidates the lineage. The server enforces this gate for direct API callers as well as the UI.

When confirmed service dates change, the previous snapshot, delivery task and confirmation events
remain immutable historical evidence, but the current schedule-confirmation Query projects that
lineage as `sent_outdated`. The change itself creates neither a new snapshot nor an outbound
delivery intent. The UI must show the current date table and its difference from the previous sent
table; only an explicit human resend may create a new snapshot and durable delivery task. Previous
confirmations never satisfy the new version's Assignment Plan gate.

2026-08-24 人工裁決：LINE 不是日期表確認的唯一入口。缺少 LINE identity／binding，或現場、電話、
紙本已完成確認時，內部操作者可先對 current confirmed-service-date version 與 current matching plan
執行人工快照 Preview，明確確認後 Apply 建立 immutable `draft` snapshot 與 customer／caregiver
recipient snapshots；不得建立或假造 LINE delivery task。每位 recipient 再以非空 reason、actor、
idempotency identity 記錄 `manually_confirmed`／`manually_revoked`。Assignment Plan gate 僅接受 current
lineage 中客戶與目標月嫂全數 `confirmed` 或 `manually_confirmed`；日期、方案、segment 或 fingerprint
異動仍使舊確認失效。若後續改走 LINE，必須保留人工歷史、明確 invalidated 後建立新的 `sent` snapshot。

### Schedule Projection

由 assignment segment、排休規則及正式 leave outcome 產生完整 assignment-owned 日曆。禁止單日 CRUD、獨立 Generate 或 UI 直接切換 `is_work_day`。

### Leave／Substitution

多日請假為一次 Preview、一個 fingerprint、一次 Apply transaction；每一天保存 immutable outcome。正式結果只允許順延或指定代班。代班建立獨立 assignment；取消或更正以反向／替代事件處理。

2026-08-12 人工裁決：月嫂請假審核的 API、typed client 與管理入口由 Scheduling 擁有，
不得掛在 LINE identity review route 或 `LineAdminApiClient`。LINE 只提供 verified identity、
delivery intent 與通知結果。現有依賴已退役 `services.*` 的 review service 是 `live-drift`，
在 canonical repository／outer UoW、capability、typed result 與 entrypoint replacement 完成前
不得掛入 FastAPI。

2026-08-15 人工裁決：LINE 月嫂請假先寫入 Scheduling request evidence，不自動猜案件、服務日、
代班人或更動 availability／正式排班。request 的 `pending`、`accepted_for_processing`、`rejected`、
`cancelled` 與 `resolved` 是獨立狀態機；只有已受理 request 能由唯一 canonical leave-substitution
receipt 關聯為 `resolved`。receipt 必須證明原 leave outcome 的 staff 與 request staff 相同，且同一
receipt 不得關聯兩筆 request。正式 Apply 的 locks、跨 Domain impacts 與 receipt 不因 request
存在而變更；LINE 通知是 committed durable delivery task，失敗不回滾正式結果。

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

與 Orders AutoComplete 的競爭契約：

- leave-substitution Apply 與 AutoComplete 必須先鎖定同一 Orders lifecycle aggregate，並驗證同一
  expected Orders lifecycle version；不得各自只鎖 Scheduling 或 Orders projection。
- AutoComplete 先提交時，舊 leave Preview 必須以 typed `stale_version`／version conflict 失敗；
  Scheduling generation、assignment／schedule、Client Finance、Payroll、leave outcome、receipt 與
  outbox 全部零寫入。
- leave-substitution 先提交時，必須在同一 transaction 更新正式服務日與 Orders lifecycle version；
  舊 AutoComplete command 必須以 `order_version_conflict` 失敗且零寫入。只有重新讀取新 effective
  generation、official service days 與新 completion instant 後，才能再次判斷完成。
- LINE leave request evidence 或管理員受理狀態不參與此競爭；只有 canonical leave-substitution
  Apply 會取得鎖並改變正式根事實。
- 任一 stale／conflict 路徑不得留下 partial batch，也不得以「先完成後補請假」掩蓋競爭。

### Assignment Lifecycle Projection

`planned`、`active`、`completed` 由正式服務時刻推導；中間休假仍 active。`cancelled` 只由命令產生；`replaced` 只作 legacy 相容。

### Calendar Read

逐日顯示 waiting lock、buffer、assignment interval、正式工作日與休假。只組合 typed ViewModel，不在 Query 或 render 時轉移狀態。

Calendar 亦顯示 current 長假／暫停接案的日期、kind 與原因。這些日期不可標為可接案、正式服務日、
assignment leave outcome 或七日 buffer；取消後保留歷史但不再出現在 current availability projection。

Calendar／React 只能顯示 Scheduling typed projection 的 `planned／active／completed` 與逐日
`assignment_status`；不得依 Orders label、瀏覽器日期、occupancy tone 或是否含案件編號自行推導「服務中」。
`assignment_buffer`／`waiting_deposit_buffer` 永不得標為服務中；完成 assignment 的歷史服務日顯示
「服務已結束」，但仍維持唯讀歷史可見性。

Calendar 的「可進行出勤精算案件」必須先以 Scheduling 的單一批次 read
`staff/{staff_id}/assignment-schedules` 取得該月嫂未取消的正式 assignment `case_no` 集合，
再與 Orders 摘要相交。不得以 `orders.staff_id`、`orders.staff_name` 或逐案
`cases/{case_no}/assignment-schedules` fallback 作為 formal-assignment 判定；前兩者可能是投影
漂移，後者會形成 N+1 read。此 query 只授權 Calendar 選案，不授權 Preview 或 Apply 寫入。

#### Calendar presentation 與案件選擇（2026-08-25 人工裁決）

- 沒有 assignment、waiting lock、buffer、不可服務期間或其他 typed occupancy 的日期，不渲染灰色
  空白占位方塊；空白日期不是一種排班事件。月嫂姓名下方只顯示 server typed 的 current 可排班狀態
  與必要人可讀原因，不得由灰階、cell 是否存在或瀏覽器日期自行推導 availability。
- 真實 assignment／lock／buffer／不可服務期間仍依各自 typed kind 顯示，不能為了移除灰塊而隱藏
  正式占用、合法唯讀歷史或 blocker。
- 「可進行出勤精算案件」改為下拉選單。選項由上述單一批次 Scheduling read 與 Orders typed summaries
  的 server／client adapter 組合取得，包含穩定 case identity 與人可讀 label；不得要求操作者手動輸入
  `case_no`，也不得使用 `orders.staff_id`／`staff_name` fallback 或逐案 N+1 查詢補選項。
- 下拉選單須有 loading、合法空、error、retry、stale request cancellation 與 identity-preserving refresh；
  options query 失敗時不掛載 Preview／Apply，且不得保留上一位月嫂的 stale 案件。
- 選定排查案件後，每位月嫂的月曆列須以一個連續區間顯示該案件的完整正式服務檔期；若完整檔期內
  任一天與 assignment、lock、buffer 或不可服務期間衝突，仍顯示整段案件檔期並將整段標示為有衝突，
  衝突天數與原因留在狀態文字／詳細排查中。不得只渲染零碎衝突日期而隱藏同案其餘服務日期。

驗收狀態（2026-08-25）：`completed`。Calendar 已以 typed 下拉選案，並依同日最新人工裁決改為
完整服務檔期連續投影；任一日期衝突時，整段檔期顯示衝突。Focused tests／React build 已通過；
最新 Chrome 實選跨月案件 `115000008`（`2026-09-05 ～ 2026-10-13`），九月投影為 9/5～9/30、
十月投影為 10/1～10/13；同一月嫂若任一天有 typed 衝突，兩個月的可見區段皆顯示整段受影響。
月份切換與清除案件後無 stale 投影或 API error。

#### Completed assignment historical projection（2026-08-12）

完成訂單與 `completed` assignment 一律可在 Calendar 唯讀查閱，完成狀態只禁止
leave／substitution 等 mutation，不得使歷史區段消失。Query 優先顯示
assignment-owned `staff_schedule.assignment_id` 的正式每日 ownership；若 historical／legacy
資料缺少該 daily ownership，但 `case_staff_assignments` 保有 completed assignment 的正式起訖日，
Calendar 必須以該區段顯示 `historical_assignment`／「歷史正式指派」。此 fallback 是歷史占用
view，不能宣稱為正式工作日、不能重算 actual hours、不能產生薪資、不能變更 availability
current projection，也不能授權任何 Apply。

同一天若同時存在 assignment-owned daily schedule、waiting lock、buffer 或其他 current fact，
該 current fact 優先；historical fallback 只填補沒有較高權威逐日事實的日期。Calendar 不得使用
`orders.actual_start_date`、`orders.staff_id`、legacy 無 `assignment_id` 的 `staff_schedule` 或 UI
自行推算，將完成案歷史誤標為「可接案」或「服務工作日」。

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
Calendar Query 必須驗證 completed assignment 在缺少 assignment-owned daily schedule 時仍回傳
唯讀 `historical_assignment`，且不覆蓋同日的 current ownership／lock／buffer，也不顯示為可接案。

### Current anomaly owner decision matrix（2026-08-31）

下表只組合本 Domain 已有的 Assignment Plan 與 Leave／Substitution Q／P／A；不新增
generic remediation 或 Anomalies writer。共同 owner readback 必須綁定 current Scheduling aggregate
version／effective generation，回報 `authoritative_complete`；owner Apply 在既有 outer UoW 內與
receipt／outbox 一併寫入 bounded `anomaly.recheck` intent。readback 不完整、stale 或 unavailable
一律 fail closed。

| Code／subject | Active predicate（current roots） | 唯一合法 owner operation | Completion predicate | Closed unresolved reasons |
|---|---|---|---|---|
| `SCHEDULE-002` / `assignment_id` | current replacement／substitution lineage 不完整：既有 assignment 已失效，但 exact successor、受影響每日 outcome、official ownership 或必要 Payroll／Finance impact 仍有缺口 | 未有任何正式服務日時使用 `Preview／ApplyAssignmentPlan`建立新 effective generation；已有正式服務日時使用 `Preview／ApplyLeaveSubstitutionBatch`只重建受影響 family | exact old/new lineage 存在，每日 outcome、official ownership、全案 coverage／hours 與必要 Payroll／Finance impacts 全部完整 | `replacement_successor_missing`, `daily_outcome_incomplete`, `service_ownership_incomplete`, `payroll_impact_incomplete`, `finance_impact_incomplete`, `owner_readback_incomplete` |
| `SCHEDULE-003` / sorted `assignment_id_a + assignment_id_b` | 兩個 current effective assignments 使同一 staff 的完整占用區間重疊 | 人員在 `Preview／ApplyAssignmentPlan` 明確選定受修正案件與 candidate；Apply 仍以 cancel-old／create-new 重建該案 current generation，並 fresh 驗證另一 assignment 的占用 | 該 canonical pair 在 current effective generations 不再重疊，兩案 coverage／ownership／hours 仍合法 | `correction_target_not_selected`, `staff_occupancy_conflict`, `coverage_incomplete`, `owner_readback_incomplete` |
| `SCHEDULE-006` / `case_no + generation` | current effective generation 的 official service dates、daily ownership、coverage、hours 或 staff occupancy 任一違反本規格，或有效服務量不等於 Orders 契約服務量 | `Preview／ApplyAssignmentPlan` 以 current Orders terms 與 Scheduling roots 重建完整 generation | 同一 current snapshot 下 official dates、ownership、coverage、hours、occupancy 與唯一 effective generation 全部合法 | `official_service_dates_invalid`, `service_ownership_conflict`, `coverage_incomplete`, `hours_mismatch`, `staff_occupancy_conflict`, `generation_conflict`, `owner_readback_incomplete` |

```yaml
convergence:
  status: READY
  requirement_ids: [SCH-ANM-002, SCH-ANM-003, SCH-ANM-006, SCH-ANM-READBACK]
  acceptance_ids: [SCH-ANM-ACTIVE, SCH-ANM-OWNER-QPA, SCH-ANM-TERMINAL, SCH-ANM-FAIL-CLOSED]
  blockers: []
```

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

### 休假／代班 Calendar Preview 補充裁決（2026-08-12）

- Preview 必須回傳零寫入的 before／after day-cell candidate 與獨立 `apply_readiness`。
- Client Finance、Payroll 或 Orders blocker 不得遮蔽已成立的 Scheduling candidate；UI 必須停用 Apply。
- 代班只替換同一服務日 owner；順延才移動服務日期。兩者都必須維持合約服務日數守恆。
- Apply 必須 fresh rebuild 並重新檢查 blocker、versions、fingerprint 與 occupancy，禁止信任 UI snapshot。
- `SchedulingHolidayQuery` 是 Preview／Apply 共用的版本化、fail-closed read port；國定假日預設為休假、扣除服務日並順延。Holiday facts 必須納入 Preview fingerprint，Apply 必須 fresh-read 並鎖定同一 planning horizon；無法讀取時回 `holiday_calendar_unavailable`。
- Holiday 管理 Query 必須回傳 closed typed rows、`source_identity`、calendar version 與明確
  planning horizon；Preview 為零寫入，Apply 以同一 horizon fresh-lock、驗 expected version 與
  fingerprint，並把 holiday mutation 與 immutable receipt 放在單一 outer UoW。Cache 只在
  commit 後失效，失效失敗不得改寫已提交 receipt。`is_double_pay_default`僅為相容參考，
  不得由 UI 或 Scheduling 自動產生 Payroll 規則。
- Leave／substitution Calendar Preview 的 API view、UI client 與 route payload 必須以同一
  `LeaveSubstitutionPreviewView` 驗證；成功 envelope 的 nullable `error` 不得被 UI 誤判為
  失敗。UI 只 render typed candidate、holiday rows 與 apply readiness。

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

## Candidate Contact Pool（2026-08-12）

Scheduling／Matching 擁有 case-owned Candidate Contact Pool。它只擁有候選月嫂聯繫事實：候選人、完整 coverage evidence、資訊-1／資訊-2 發送事件與 delivery 狀態、月嫂意願、拒絕理由、人工補登 actor／時間。它不是 `caregiver_matching_plans` 或 `caregiver_matching_plan_segments`，不得建立 availability lock、正式 assignment、staff schedule、日期表 snapshot、客戶履歷傳送或正式指派資格。

- 一次可加入多位對目前預計服務日期有完整 coverage 的候選人；加入與每次資訊發送皆須 fresh-read availability。
- 發送資訊-1／資訊-2 是詢問接案意願的唯一聯繫動作；不得另建沒有資料效果的「聯繫與確認意願」命令。
- 每位候選人的意願及兩種資訊寄送紀錄獨立、append-only 且以 candidate entry／event key 冪等；不得由同案其他候選人覆蓋。
- 管理員僅能從 `willing` 候選人選定一位，重新檢查可用性後建立一個 segment 的正式 matching plan。
- 多位月嫂共同服務仍是顯式 multi-caregiver fallback plan，不能由候選聯繫池直接轉換。
- 選定、撤回或取消不得刪除候選聯繫歷史。正式 plan 後的日期表、客戶與月嫂雙方確認及 assignment gate 僅針對該正式 plan recipients。

### 人工媒合確認（2026-08-24）

LINE identity、recipient binding 或 delivery 缺漏時，已登入的內部操作者可透過正式 matching-plan
manual response 記錄特定 segment 的月嫂意願與客戶決策。每筆皆須 actor、非空 reason、目前 plan
version、idempotency identity 與回讀；不得偽造 LINE delivery 或省略正式 plan recipient。LINE callback
仍必須驗證 recipient／delivery state。客戶接受仍只形成 matching decision，後續鎖定、契約與 execution
各自遵守其既有 Preview／Apply gate。

## Historical pairing evidence（2026-08-13）

Historical Order Adoption 可保存一或兩位來源月嫂的不可變配對 evidence。月嫂姓名空白、找不到或
不唯一都不阻擋 Orders status adoption；只形成 bounded review。單一月嫂且共同起訖日可唯一視為
該月嫂自己的歷史區間時，可由 purpose-specific Scheduling writer 建立 `completed`
`case_staff_assignments`。兩位月嫂只有共同起訖日、沒有每人各自區間時，不建立正式 assignment、
不猜測分段，也不寫 `orders.staff_id` 或 `staff_schedule`。

歷史 assignment 即使有起訖日，仍不等於 assignment-owned official service days。缺少逐日 ownership
與 rate snapshot 時 Payroll 固定回 blocker；不得按連續曆日猜算工時、薪資或應付義務。

## 2026-08-21 M3 Matching Coordination amendment

Scheduling 正式收納 `Matching Coordination` 為本 Domain 內的 subsystem／bounded coordination capability；它擁有 criteria snapshot、candidate/package、decision lineage 與 fresh rematch orchestration，但不擁有 Orders terms、正式 assignment、official service dates、leave outcome 或 Payroll obligation。

- `accepted` 只代表 customer decision；後續必須 fresh-read downstream effects，最多產生 typed Assignment conversion/rematch request 或 reference。Matching Coordination 不寫 Orders、Assignment 或 Payroll。
- Phase D 只能透過 typed ports 讀取 Scheduling Leave／Assignment canonical receipt、提交 conversion/rematch request 並保存 reference；不得接管 `leave_substitution`、`assignment_plan` 或其 root writer。
- Query 唯讀、Preview 零寫入、Apply 仍由 owning workflow 取得 fresh facts、lock、single outer UoW 與 receipt；跨域協調不改變本 Domain 的 assignment／leave／service-day SSOT。
- 首次建立 criteria snapshot 的 Preview 沒有既存 snapshot 可供瀏覽器取得 source tuple，必須由後端 fresh-read owner facts 並在回應中回傳 canonical tuple；該 Preview 不接受 client source-version assertion。後續 Apply 必須攜帶 Preview 回傳的完整 canonical tuple 與 fingerprint，並重新 fresh-read 驗證。
- M3 Phase E schema 只屬候選 inventory／spec planning，未授權 DDL、seed、backfill、destructive 或資料庫操作；若需變更，另立 approved schema Work Package 並重跑全部 DB gates。

---
doc_type: work-package
declared_status: completed
identity: PROV-20260821-matching-coordination-successor-contract
date: 2026-08-21
owner: Scheduling / Matching Coordination Integration Owner
domain: Scheduling / Orders / Payroll / LINE Delivery
source_gap: PROV-20260817-react-admin-phase3e-order-matching-formal-recommendation-gap
related_gaps:
  - PROV-20260816-react-admin-phase3b2-leave-substitution-public-contract-uow-gap
  - PROV-20260817-react-admin-phase3b2-leave-request-date-coverage-decision-gap
  - PROV-20260817-line-notification-manual-replay-contract-gap
approval_required: human-exact-successor-contract-and-work-package-approval
---

# M3 Matching Coordination successor contract／工作包

## 0. 狀態、目的與授權邊界

本文件是 M3 matching coordination 的 successor contract 與候選 Work Package，狀態為
`approved`；M3-A（Phase A）exact implementation 已核准且 current foundation 已實作，M3 Phase B–D
production implementation 亦已取得最新人工核准，執行狀態為 `in-progress`。核准範圍仍不包含 Phase E
schema／DDL／DB、migration、LINE provider 實際發送、Orders／Assignment／Payroll root writer 或部署；
M3 只能透過既定 typed port／durable reference 協調 owning workflow。M3-A actual write set 為下列
Phase A paths 加上本文件同步；下文 Phase B–D 的 exact write set 已獲核准並按小階段執行，Phase E
仍是待另行核准的 provisional schema candidate。

本包收斂下列真實情境：

1. 案件條件改變時，顯示 criteria diff，依穩定 rejection reason 精準重送受影響候選，而不是重送
   全池或用自由文字猜原因。
2. 候選池的 willingness 可隨時間變動；每次選定、通知、重算都使用 current pool 與 availability。
3. 零候選時可提出 deterministic、明示放寬規則的 compromise；不得 silent relax。
4. 客戶接受選定方案後，必須 fresh-read downstream effects；若日期、檔期、在職或 incumbent facts
   已變更，進入 rematch，而不是假設可直接指派。
5. 請假／代班的 `defer` 與 `substitute` 以及 due／service-date 變更都會觸發可追溯的 rematch，
   但不能越權寫入 Orders、正式 assignment、Payroll 或 LINE provider。

### 0.1 非目標

- 不建立第十三個業務 Domain；Matching Coordination 是 Scheduling 內的 subsystem／bounded
  coordination capability。
- 不擁有 Orders 的條款、due date、service date 或 lifecycle；不擁有正式 assignment、schedule、
  occupancy、leave outcome 或 waiting-deposit lock。
- 不把 customer `accepted`、caregiver `willing`、LINE delivery success 或 matching receipt 當成
  contract completion、formal assignment、Payroll obligation 或 order success。
- 不在本包自動套用 DB migration、改正式 schema、重建 production data、送真人 LINE、部署或 cutover。

## 1. 權威、owner 與邊界

### 1.1 四層定位

| 層級 | M3 允許責任 | 明確禁止 |
|---|---|---|
| Scheduling Matching Coordination | immutable criteria snapshot、matching package、candidate/result、decision lineage、fresh rematch orchestration、typed query／preview／apply | 寫 Orders terms、正式 assignment／schedule、Payroll obligation、LINE provider |
| Orders | service date、due date、service hours、cooking／baby／地域等正式 terms 與其 version | 接收 Matching UI payload 作為條款；由 M3 推導服務日 |
| Assignment workflow | waiting-lock／confirmation gate 後建立正式 assignment、official service dates、occupancy、leave／substitution outcome | 接受 customer accepted 直接建 assignment；跳過 fresh matching lineage |
| Payroll | 只由 assignment-owned official service days 建立 immutable service-day obligation | 讀 candidate、customer consent、LINE receipt 或 Orders planned hours |
| LINE Integration／Delivery | durable interaction／delivery intent、recipient binding、attempt、retry、rejection-reason interaction | 擁有 matching state、criteria、consent、contract、assignment、Payroll；provider failure 不回滾已提交業務事實 |

Orders、Assignments／Scheduling、Payroll、LINE 的正式規格仍分別以 `15`、`02`、`21`、`24` 與
`17` 為準；本文件只能提出 successor contract，不取代人工核准的 current SSOT。

### 1.2 SSOT 與根事實

- `OrdersTermsFact`：Orders 的 terms／service-date／due-date root 及其 version。
- `SchedulingAvailabilityFact`：assignment interval、waiting lock、buffer、unavailability、
  current effective generation 及其 version；同一份 current facts 同供 Calendar 與 Matching。
- `StaffMatchingProfileFact`：偏好 definition/value version、staff lifecycle state version。
- `MatchingCriteriaSnapshot`：M3 建立的不可變 canonical criteria、source-version tuple、digest、
  actor／occurred-at；禁止原地修改。
- `MatchingPackage`：一個完整 single-caregiver 或顯式 multi-segment proposal 的不可變 segments、
  coverage proof、ranking、per-condition result、rejection reason、candidate lineage 與 package version。
- `MatchingDecisionLineage`：candidate contact、willingness、customer decision、selection、
  criteria diff、compromise、rematch、superseded／stale 事件的 append-only lineage。
- `AssignmentConversionReceipt`：只由 Assignment workflow 產生；M3 僅保存 reference／result，
  不把 request 或 accepted decision 投影成 assignment。
- `PayrollOfficialServiceDayReceipt`：只由 Payroll 接收 Assignment-owned official service-day
  facts 後建立；M3 不建立或重算。

### 1.3 Source-version tuple

每個 Query／Preview／Apply response 必須帶完整、排序穩定的 tuple；未讀取的來源不得以 `0` 或
目前值假裝相容。tuple 每項至少包含 `source_kind`、`source_id`、`version`、`fingerprint`：

```text
(orders_terms,
 orders_service_dates,
 scheduling_availability,
 scheduling_effective_generation,
 staff_profile_definition,
 staff_profile_values,
 staff_lifecycle,
 matching_criteria_snapshot,
 candidate_pool,
 matching_package,
 incumbent_assignment,
 leave_request_or_outcome,
 assignment_conversion_reference)
```

不適用項目明確標 `not_consulted`，不得省略。Orders terms／日期的 source identity 由 Orders
提供；M3 不自行從地址、自由文字或 UI state 推導日期、下廚或雙胞胎條款。

## 2. 不可破壞的 contract invariants

1. Criteria snapshot、package、candidate rejection、decision、rematch 與通知 source lineage 都是
   immutable event／version；不得用 mutable current projection 取代歷史理由。
2. 每一個 candidate 的每一條 criteria result 都以 machine-stable code 保存；顯示名稱可變但不能作
   decision rule。`criteria_diff` 必須可重算、可比較且有 digest。
3. Single caregiver coverage proof 必須涵蓋全部 current confirmed service dates；若無法涵蓋，
   只能提出明確 2–4 個連續、無重疊 segments 的 multi-caregiver package。不得由候選數量或 UI 多選
   推導正式方案。
4. Candidate pool willingness、staff availability、lifecycle 與 incumbent facts 都是 dynamic facts；
   任何 selection／consent／resend／rematch Apply 前必須 fresh-read and lock。
5. Customer `accepted` 僅表示客戶對目前 matching package 的 decision event；不等於 contract completed、
   waiting lock converted、formal assignment、official service date 或 Payroll obligation。
6. Leave `defer` 移動服務日期、`substitute` 替換同一服務日 owner；兩者均須由 Scheduling Leave／Assignment
   workflow Preview／Apply，維持 contract service-day conservation，不得由 M3 直接改日期或 staff。
7. Orders due／service-date／terms change 使舊 criteria/package/consent 的 lineage `stale` 或
   `rematch_required`；舊確認可查閱但不得滿足新 package 或 Assignment gate。變更不自動外送，只有
   explicit resend Apply 才能產生新 LINE intent。
8. Zero-candidate compromise 只能採用 server 產生且有固定 policy id、放寬欄位、風險／warning、排序及
   fingerprint 的 alternative；沒有 silent relax、client-side fallback 或「先套用再補理由」。
9. Query 唯讀；Preview 零寫入；Apply fresh-read／lock／rebuild 後才 commit。所有 mutation 僅有一個
   single outer Unit of Work／commit owner；repository／adapter 不 hidden commit。
10. 外部副作用只由 committed outbox／durable job 執行。LINE delivery failure、timeout 或 exhausted
    不偽造 Matching success，也不回滾已提交 root facts。

## 3. State machines

### 3.1 Criteria snapshot／package

```text
criteria_requested → snapshotted → evaluated
snapshotted/evaluated → superseded | stale

candidate_pool_open → proposed
proposed → awaiting_caregiver_willingness
awaiting_caregiver_willingness → awaiting_customer_decision | no_candidate | rematch_required
awaiting_customer_decision → accepted | declined | expired | rematch_required
no_candidate → alternative_previewed → alternative_applied | no_candidate_terminal
accepted/declined → superseded (only by a newer explicit package lineage)
```

`no_candidate_terminal` 是可稽核的結果，不是錯誤地把「沒有方案」轉成可指派。`alternative_previewed`
只存在於零候選的 explicit compromise preview；Apply 必須引用同一 `alternative_id` 與 fingerprint。

### 3.2 Candidate／willingness／resend

```text
candidate_seen → contact_pending → contact_queued → willingness_pending
willingness_pending → willing | unwilling(reason_code) | expired | stale
unwilling/expired/stale → recontact_previewed → recontact_queued (explicit Apply only)
```

重送命令必須指定 candidate、原 notification event、new criteria snapshot、criteria diff digest 與
stable rejection reason；不能用「全部候選重送」或改寫舊 event。`unwilling.detail` 只能是 bounded
display evidence，不得取代 code 或作分支條件。

### 3.3 Customer decision 與 rematch

```text
customer_pending → presented → accepted | declined | contact_requested | expired
accepted → fresh_effects_check
fresh_effects_check → conversion_reference_requested | rematch_required | rejected_as_stale
rematch_required → criteria_diffed → re-evaluated → presented | no_candidate | alternative_previewed
```

`conversion_reference_requested` 只代表提交給 Assignment workflow 的 typed/durable request 或等待
其 fresh conversion result；不得由此狀態直接建立 assignment／schedule／Payroll。

### 3.4 Leave／date integration

```text
current_package → leave_or_date_change_detected → stale/rematch_required
leave_preview → defer_candidate | substitute_candidate
defer_candidate/substitute_candidate → Scheduling Apply receipt
Scheduling receipt → new criteria snapshot → rematch_required
```

Leave request 的 `pending`、`accepted_for_processing`、`rejected`、`cancelled`、`resolved` 仍由
Scheduling Leave intake 擁有；M3 只保存 typed reference。缺少日期 coverage 的規則未經人工裁決前，
不得由 M3 補上 predicate。

## 4. Typed public contract

### 4.1 Commands

以下是 provisional command names；每個 command 都必須帶 `actor`、`reason`、`correlation_id`、
`idempotency_key`、expected source-version tuple（依命令實際讀取的完整 subset）與 canonical fingerprint：

- `QueryMatchingCoordination`：唯讀 current criteria／package／candidate result／decision lineage。
- `PreviewMatchingPackage`：以 Orders／Scheduling／Staff typed facts 建立 immutable-candidate preview。
- `PreviewCriteriaDiffResend`：比較兩個 criteria snapshot，列出受影響 candidate、stable reason 與
  精準 notification recipients；零寫入。
- `ApplyCriteriaDiffResend`：fresh-read 後只建立選定 recipient 的 Matching event＋LINE durable intent。
- `PreviewZeroCandidateAlternative`／`ApplyZeroCandidateAlternative`：顯式採用 server policy alternative；
  不可把 soft-criteria 放寬藏在一般 Apply。
- `ApplyCaregiverSelection`：記錄 selection／willingness decision，fresh-check downstream effects，
  必要時回 `rematch_required`；不建立 assignment。
- `ApplyCustomerMatchingDecision`：記錄 customer decision；`accepted` 僅進 fresh-effects-check。
- `PreviewRematch`／`ApplyRematch`：以新 criteria／availability／incumbent facts 形成新 package lineage。
- `PreviewLeaveImpactOnMatching`／`ApplyLeaveImpactOnMatching`：只協調與 Scheduling canonical leave／
  substitution receipt 的 lineage，不越權執行 leave outcome。
- `PreviewServiceDateChangeRematch`／`ApplyServiceDateChangeRematch`：Orders 變更後重新評估；不改 Orders。

`Apply` 的 request 必須同時傳 `criteria_snapshot_id`、`package_id/version`（若適用）、
`preview_fingerprint`、`expected_source_versions`、actor／reason；缺欄或 pair mismatch 在 route boundary
即 422 且 application 零呼叫。

### 4.2 Typed views

成功 envelope 只回 typed view，raw `dict[str, Any]` 不得穿透 API／UI：

- `MatchingCriteriaSnapshotView`：`snapshot_id`、`case_no`、`criteria_version`、canonical criteria、
  `source_versions`、`fingerprint`、`created_at`、`superseded_by`。
- `MatchingCandidateResultView`：`candidate_id`、`staff_id`、package eligibility、每條
  `criteria_result(code, status, source_version)`、`rejection_reasons[]`、coverage evidence、willingness、
  `notification_lineage[]`。
- `MatchingPackageView`：`package_id/version`、single／multi mode、ordered segments、coverage／continuity／
  overlap proof、ranking、criteria snapshot、source tuple、blockers、warnings、decision state。
- `CriteriaDiffView`：before／after snapshot identity、changed fields、added／removed／unchanged stable
  reasons、affected candidate／recipient IDs、resend eligibility、diff fingerprint。
- `ZeroCandidateAlternativeView`：`alternative_id`、policy id/version、relaxed criteria、unchanged hard
  criteria、candidate result、risk warnings、deterministic rank、preview fingerprint。
- `MatchingDecisionView`：decision event identity、actor/source、candidate/package lineage、customer／
  caregiver state、`accepted_is_not_contract_or_assignment` marker、fresh-effects status、rematch reference。
- `MatchingApplyReceipt`：receipt identity、command／preview fingerprints、source tuple、decision/package
  lineage、outbox intent IDs、result state；不得含 LINE provider success 或 Payroll success。

### 4.3 Stable errors and blockers

至少凍結下列 machine-stable codes（message 可本地化，UI 不以 message 分支）：

`matching_case_not_found`, `matching_criteria_invalid`, `matching_criteria_source_stale`,
`matching_criteria_diff_required`, `matching_package_not_found`, `matching_package_stale`,
`matching_source_version_conflict`, `matching_candidate_not_found`, `matching_coverage_incomplete`,
`matching_service_date_conflict`, `matching_unavailability_conflict`, `matching_staff_retired`,
`matching_preference_source_not_ready`, `matching_preference_mismatch`, `matching_willingness_pending`,
`matching_willingness_conflict`, `matching_rejection_reason_required`, `matching_recontact_source_stale`,
`matching_no_candidate`, `matching_alternative_not_explicit`, `matching_alternative_stale`,
`matching_customer_decision_conflict`, `matching_customer_acceptance_not_conversion`,
`matching_incumbent_unavailable`, `matching_rematch_required`, `matching_leave_reference_stale`,
`matching_leave_resolution_not_applied`, `matching_assignment_conversion_pending`,
`matching_assignment_conversion_mismatch`, `matching_idempotency_conflict`,
`matching_invalid_replay_snapshot`, `matching_lock_set_stale`, `matching_transaction_failed`。

Stable rejection reason enum 至少包含：`region_mismatch`、`service_date_conflict`、`unavailable_period`、
`waiting_lock_conflict`、`buffer_conflict`、`staff_retired`、`preference_not_ready`、
`preference_mismatch`、`coverage_incomplete`、`line_binding_missing`、`willingness_unconfirmed`、
`incumbent_occupied`、`due_date_outside_window`、`criteria_source_stale`、`candidate_expired`。
`no_candidate` 是 package outcome，不得冒充某一位 staff 的 rejection reason。

## 5. Query／Preview／Apply、transaction 與 replay

### 5.1 Query

Query 唯讀載入 current Orders／Scheduling／Staff／Matching typed facts，回完整 source tuple、criteria／
package lineage、per-candidate results、stable rejection reasons、LINE delivery projection 與 blockers。
不建立 lock、receipt、notification 或 decision event；無資料只回 typed empty／`matching_case_not_found`，
不得由 UI 猜測 stage。

### 5.2 Preview

Preview 僅做 read-side candidate build，禁止 DB write、event、receipt、outbox、LINE enqueue、waiting lock、
assignment 或 Payroll。它必須回：criteria snapshot／diff、candidate/package、coverage proof、dynamic
willingness、downstream impact references（Orders／Assignment／Payroll read-only facts）、hard blockers、
warnings、explicit alternative（若 zero candidate）及 server fingerprint。任何 source unavailable、
partial fact、未知 rejection 或 criteria ambiguity 都 fail closed。

### 5.3 Apply

Apply 流程固定為：

```text
authorize → idempotency claim/replay lock → lock case/matching root
→ lock Orders terms/date root → lock staff mutex IDs ascending
→ lock candidate pool/package/decision lineage
→ fresh-read Scheduling availability/leave/incumbent/lifecycle
→ rebuild same candidate builder → validate source tuple/preview fingerprint/alternative policy
→ append Matching decision/package/rematch lineage
→ create committed outbox/durable intent (LINE or Assignment request only)
→ immutable receipt/result snapshot → one outer commit
```

M3 不在上述交易內寫 Orders、Assignment、Payroll 或呼叫 LINE provider。若需正式 assignment，
`AssignmentConversionRequested` 只可作為 committed durable job／typed port request，並且要附 exact
package／criteria lineage；Assignment workflow 另以自身 fresh Preview／Apply、confirmation、waiting-lock
與 single UoW 產生 assignment。若 fresh facts 改變，Apply 必須零 partial write 回 `rematch_required`。

鎖定後若 impacted staff set 擴張、source tuple drift、incumbent 已被替換、due／service date 已改或
leave receipt 未完成，固定回 stale/conflict；不得中途取得第二套 mutex、改用較寬條件或自動換 key。

### 5.4 Idempotency、replay、timeout

- `same idempotency_key + same command fingerprint`：只讀 immutable receipt/result snapshot，零重建、零
  notification enqueue、零 assignment request duplicate。
- 相同 key 搭配 actor／reason／criteria／package／source tuple／preview fingerprint 任一不同：
  `matching_idempotency_conflict`，零寫入。
- receipt snapshot 缺欄、extra 欄、lineage／tuple mismatch、child event 缺號或重複：
  `matching_invalid_replay_snapshot`，不得自動補寫；轉人工 recovery。
- DB deadlock／lock timeout／provider unavailable 可用相同 identity bounded retry；domain blocker、
  stale、criteria diff、recipient mismatch 不 retry。HTTP timeout 的 unknown outcome 先 Query receipt，
  不得換 key 重送。

## 6. Criteria diff、willingness、compromise 與 rematch 規則

### 6.1 精準重送

Criteria diff 必須逐欄區分 `added`、`removed`、`changed`、`unchanged`，並以 stable reason code 映射
受影響 candidate。只允許對「新 criteria 下仍可送、且原 rejection reason／criteria diff 與 recipient scope
符合」的 recipient 產生新 intent。新通知 payload 保存 old/new snapshot IDs、diff fingerprint、reason
code、candidate/package lineage、source tuple；LINE 只負責 delivery／interaction。既有 delivery task、
rejection 或 willingness event 不可覆蓋或刪除。

### 6.2 Dynamic willingness pool

每次 contact／resend／selection 前重新讀 current candidate pool、availability、unavailability、staff
lifecycle、preference version 及 LINE binding。`willing` 不是永久 qualification；失效只追加
`candidate_expired`／`criteria_source_stale` lineage，不能靜默保留在 package。`unwilling` 必須有 stable
reason code；manual override 另需 actor／reason／expected version，不能把手工勾選直接當 willing。

### 6.3 Zero-candidate deterministic compromise

若所有 hard criteria 都無候選，Server 可依核准 policy version 產生 alternative。Policy 必須固定：
hard／soft criteria、一次可放寬欄位、候選排序 tie-break、風險 warning、需要的人工確認與 expiration。
Preview 顯示完整 before／after；Apply request 必須帶 `alternative_id`、policy version、relaxed fields、
preview fingerprint，Apply 後再 fresh rebuild。未經 explicit alternative Apply，原 package 維持
`no_candidate`，不得建立 contact、consent、waiting lock、assignment 或 Payroll。

### 6.4 Accepted selection 後 fresh effects／rematch

Customer accepted 後立即以 current Orders／Scheduling／Staff／incumbent／leave facts 重新驗證：
coverage、service dates、availability、lifecycle、waiting lock eligibility、schedule-confirmation lineage
與 assignment conversion prerequisites。fresh conversion 只有在明確指定目前 package 中
`eligibility=eligible` 且 `willing=willing` 的 candidate 時才可建立；缺少 candidate 固定回
`matching_customer_acceptance_not_conversion`，willingness／eligibility 不符且 fresh effects
仍相符時固定回 `matching_willingness_conflict`。若 fresh effects 已不相符，只建立
`rematch_required` view／lineage；不建立
assignment、不發 Payroll impact、不宣稱契約完成。只有 Assignment workflow 的正式 conversion receipt
才可使 Payroll 讀取 official service-day obligations。

## 7. Due／service-date、incumbent availability 與 leave/substitution integration

- Orders 只接受 Orders typed command 改 due／service dates／terms；M3 監看其 version／event，建立
  criteria diff，將 current package／consent 投影為 `stale` 或 `rematch_required`。
- Scheduling 的 unavailability／incumbent assignment／waiting lock／buffer 變更只由 Scheduling owner
  建立；M3 Query 可讀、Apply fresh 驗證，不重算或寫入其根事實。
- `defer` 只承接 Scheduling Leave outcome reference，代表 official service date 移動；`substitute`
  只承接同日 staff-owner replacement。兩者都必須有 canonical receipt、source tuple 與 fresh matching
  re-evaluation；缺 receipt、staff mismatch、date coverage 未裁決均回 stable blocker。
- Existing confirmed schedule snapshot 在 service-date change 後成為 historical/outdated；LINE 不自動
  resend。只有新 criteria/package Preview 通過後的 explicit resend Apply 才可建立新 durable task；舊
  confirmations 不滿足新 Assignment gate。
- Incumbent unavailable（leave、retired、new lock、date conflict）不由 M3 取消 assignment；只建立
  typed `rematch_required` 與 Assignment／Leave recovery reference，由人員走 owning workflow。

## 8. Ports、outbox 與人工 recovery

### 8.1 Typed ports

`OrdersTermsQueryPort`、`OrdersServiceDateQueryPort`、`SchedulingAvailabilityQueryPort`、
`SchedulingLeaveReferencePort`、`StaffMatchingProfileQueryPort`、`StaffLifecycleQueryPort`、
`CandidatePoolRepository`、`MatchingCoordinationRepository`、`AssignmentConversionQueryPort`、
`AssignmentConversionRequestPort`、`PayrollOfficialServiceDayQueryPort`、`LineInteractionIntentPort`、
`OutboxPort`、`ReceiptRepository`、`BusinessClock`、`UnitOfWork`。

所有 port 只接受／回傳 typed facts；不得回 raw persistence mapping。LINE port 建立 durable intent，
不直接發 HTTP；Assignment port 建立 typed request／query reference，不直接寫 assignment。

### 8.2 Outbox與通知

Matching event commit 後才可 enqueue `LineMatchingInteractionIntent`、`LineCriteriaDiffResendIntent`
或 `AssignmentConversionRequested`。每一 intent 必須帶 source event identity、criteria/package digest、
recipient scope、stable reason／diff、idempotency identity；provider attempt、retry、exhausted 是
LINE delivery projection，不是 M3 success。LINE delivery failure 進 anomaly／manual queue，不回滾 M3。

### 8.3 人工 recovery（manual recovery）

人工入口只允許：重新 Query source tuple、Preview criteria diff／rematch／explicit alternative、
確認 stable blocker、Apply 同一 preview、查 receipt／outbox／delivery task、重送同一 intent 或以新
criteria snapshot 建立新 intent。不得用 Data Browser、SQL、order status、UI local state 直接補
criteria、willingness、assignment、service date 或 Payroll。replay corruption、未知 source、partial
lineage、outbox exhausted、incumbent conflict 都要保留 anomaly／review item，等待 owning Domain 人工
command；resolve 待辦不等於 root fact 已修復。

## 9. 分 Phase provisional implementation scope

以下依目前授權狀態列出 exact write set。任何 path 需與最新 base ref 重查；
若人工核准改變 owner、SSOT、public interface、transaction 或 schema，必須另立 successor／更新本包，
不得自行擴張。M3-A actual write set 為下列 Phase A paths 加上本文件同步；Phase B–D 已核准且執行中，
Phase E 仍是 provisional、未授權。

### Phase A — contract/domain freeze（M3-A：已核准且已實作）

**Approved exact write set**

- `domains/scheduling/matching_coordination.py`（new：snapshot/package/result/lineage pure rules）
- `subsystems/scheduling/matching_coordination_contracts.py`（new：commands/views/errors）
- `subsystems/scheduling/matching_coordination_workflow.py`（new：Query／Preview／Apply orchestration）
- `tests/test_matching_coordination_domain.py`
- `tests/test_matching_coordination_contracts.py`
- `tests/test_matching_coordination_workflow.py`

**Implementation status**：M3-A foundation 已實作；本階段仍不包含 API、DB、LINE provider 或
Orders／Assignment／Payroll root write。

**Acceptance**：純 modules 不讀 DB／clock／network；criteria/package immutable；single/multi coverage、
stable reason、source tuple、customer accepted non-conversion、explicit alternative、state transition、
fingerprint／idempotency／stale 的 contract tests 通過；無 API、DB、LINE provider 或 assignment write。

### Phase B — typed query與dynamic candidate pool（已核准，執行中）

**Approved exact write set（implementation in progress）**

- `subsystems/scheduling/matching_coordination_query.py`（new）
- `subsystems/scheduling/candidate_contact_pool_workflow.py`
- `infrastructure/mysql/matching_recommendation_repository.py`
- `infrastructure/mysql/matching_notification_repository.py`
- `api/routes/candidate_contact_pool.py`
- `api/schemas/candidate_contact_pool.py`（new）
- `tests/test_matching_coordination_query.py`
- `tests/test_candidate_contact_pool_workflow.py`
- `tests/test_matching_recommendation_query.py`
- `tests/test_candidate_contact_pool_public_contract.py`（new）

**Acceptance**：Query 零寫入；candidate contact、willingness、availability、lifecycle、preference、
criteria diff 都是 typed view；每條 rejection reason stable；fresh availability；同 key replay／payload
mismatch／missing binding／retired／dynamic willingness tests 通過；禁止 raw dict、hidden commit、由
candidate pool 直接建立 formal plan／assignment。

### Phase C — consent、精準重送與rematch（已核准，執行中）

**Approved exact write set（implementation in progress）**

- `subsystems/scheduling/matching_coordination_workflow.py`
- `subsystems/scheduling/matching_notification_contracts.py`
- `subsystems/scheduling/matching_notification_application.py`
- `subsystems/scheduling/matching_schedule_confirmation.py`
- `infrastructure/mysql/matching_schedule_confirmation_repository.py`
- `tests/line/subsystems/test_line_matching_notification_contracts_stage7.py`
- `tests/line/subsystems/test_line_matching_notification_application_stage7.py`
- `tests/test_matching_schedule_confirmation.py`
- `tests/test_matching_coordination_consent_and_rematch.py`（new）

**Acceptance**：caregiver／customer decision state machine、recipient binding、criteria diff×stable reason
精準 resend、outbox after commit、LINE provider failure isolation、accepted→fresh-effects→rematch、
outdated confirmation 與 same-key replay 通過 isolated tests；customer accepted 不產生 contract／assignment／
Payroll；LINE 只持有 durable interaction／delivery。

### Phase D — leave／date integration與incumbent availability（typed ports only；已核准，執行中）

**Approved exact write set（implementation in progress）**

- `subsystems/scheduling/matching_coordination_workflow.py`
- `subsystems/scheduling/matching_coordination_contracts.py`（新增 leave／assignment typed ports；不擁有 root writer）
- `subsystems/scheduling/matching_leave_integration.py`（new；只保存 canonical receipt／reference）
- `subsystems/scheduling/matching_assignment_conversion.py`（new；只提交 typed conversion/rematch request）
- `tests/test_leave_substitution_workflow.py`
- `tests/test_assignment_plan_workflow.py`
- `tests/test_matching_coordination_leave_and_date_rematch.py`（new）
- `tests/test_matching_coordination_incumbent_conflict.py`（new）

**Acceptance**：leave defer／substitute 只承接 canonical Scheduling receipt；due／service-date version diff
觸發 stale/rematch；incumbent leave／retired／availability conflict 不取消 assignment、不寫 Payroll；
Scheduling single outer UoW、fresh lock、rollback、stale、receipt lineage、AutoComplete competition 與
Assignment confirmation gate regression 通過；尚未裁決的 leave date coverage 固定 fail closed。

### Phase E — optional additive schema candidate（未授權）

**Candidate classification only**：可能需要 additive `schema-only` objects 保存 immutable criteria snapshot、
package／segment、criteria result／stable reason、decision／rematch lineage、source-version tuple、
replay receipt／outbox lineage。現階段沒有 system-seed、business-row-backfill 或 destructive change；
不宣稱既有 tables 足夠，也不宣稱任何 DDL 已核准。

**Provisional write set（只有人工核准後 late-bind 才能建立）**

- `db/schema_parts/PROV-20260821-matching-coordination-successor.sql`
- `db/migration_releases/PROV-20260821-matching-coordination-successor.release.json`
- `db/migration_releases/PROV-20260821-matching-coordination-successor.descriptors.json`
- `tests/test_matching_coordination_schema_contract.py`
- preserve-data rehearsal plan／receipt（由 integration owner 另行配號）

**Acceptance**：只有 Scope、inventory、static release、descriptor、read-only plan、fresh bootstrap、
preserve-data candidate upgrade、rollback／replay／drift evidence 全部通過後，才可另取得 developer DB
操作授權；不得操作 `union_db` 或把 schema candidate 當 production release。

## 10. DB change gate（本文件結論）

| Gate | Status | Evidence／限制 |
|---|---|---|
| Scope gate | **PASS** | 人工已核准 Scheduling Matching Coordination subsystem 與 Phase A–D specification freeze；Phase E 僅 candidate inventory／planning，無 schema implementation 授權。 |
| Change inventory | **PASS** | 僅做 candidate classification：schema-only 可能新增 immutable lineage；system-seed、business-row-backfill、destructive 均 `none proposed`。未產生 DDL。 |
| Static release gate | **NOT_RUN** | 尚無 canonical release、assembly／manifest、dependency 或 approved artifact。 |
| Descriptor gate | **NOT_RUN** | 尚無 altered parent／owned-object descriptor；不得假設既有 table exact。 |
| Read-only plan gate | **NOT_RUN** | 無 release artifact 可供 plan；不得以 launcher dry-run 代替 migration plan。 |
| Engine verification gate | **NOT_RUN** | 未執行 disposable MySQL fresh bootstrap 或 preserve-data candidate；不得以 mock／compile 宣稱通過。 |
| Developer acceptance gate | **NOT_RUN** | implementation／DB mutation 未授權；不操作任何既有資料庫，尤其 `union_db`。 |

結論：`DB_CHANGE_NOT_READY`。本文件不授權 schema、seed、backfill、migration、production data、
deployment、LINE 外送或任何 external side effect。

## 11. Required approval與驗收證據

人工核准必須逐項確認：

1. M3 owner 為 Scheduling Matching Coordination subsystem，且不新增 Domain。
2. Orders、Assignment workflow、Payroll、LINE 四方 owner／依賴與 `accepted != contract/assignment/payroll`
   不變量。
3. criteria snapshot／package／decision lineage 的 identity、source tuple、state machine、stable
   rejection reason、criteria diff resend、dynamic willingness 與 zero-candidate policy。
4. Query／Preview／Apply、single outer UoW、lock order、replay／stale／timeout／conflict、outbox 及 manual
   recovery contract。
5. Phase A–D 的 exact provisional write set 與 Phase E 是否需要 additive schema；任何變更須回本包或另立
   successor，不能以人工口頭默認擴張。
6. 驗收需包含 pure module、typed boundary、isolated MySQL transaction／rollback／replay、criteria diff
   resend、zero-candidate alternative、accepted rematch、leave defer／substitute、due/service-date change、
   incumbent availability、LINE delivery failure isolation 與 Assignment／Payroll non-conversion。

本文件已 `approved`；M3-A（Phase A）exact implementation 已核准且 current foundation 已實作，M3
Phase B–D production implementation 已核准並進入 `in-progress`，Phase E schema 仍未授權。文件被核准
不等於 M3 full、schema、DB、LINE provider 實際發送或 deployment 已完成。

## 12. 2026-08-21 人工裁決：M3 coordination freeze

- M3 owner 固定為 Scheduling Matching Coordination subsystem，不新增 Domain；Orders、Assignment workflow、Payroll 與 LINE 各自保留 root writer。
- `accepted` 只記錄 customer decision，接著 fresh-effects check；成功時最多產生 typed `AssignmentConversionRequested`／rematch request 或 durable reference。M3 不寫 Orders、Assignment、正式 service dates、Payroll 或 provider。
- Phase A implementation 已核准且 current foundation 已實作；Phase B–D production implementation 已核准，
  現以 `in-progress` 狀態依各自 exact write set 執行。Phase D 只能經 typed ports 讀取 leave／assignment
  canonical receipt、提交 conversion/rematch request 並保存 reference；不得競寫 `leave_substitution`、
  `assignment_plan` 或其 repository／root facts。
- Phase E 僅凍結 candidate inventory／spec planning：schema-only candidate、0 system seed、0 business-row-backfill、0 destructive；不得產生或套用 DDL、release、migration 或 DB data change。
- 所有未完成的 module／subsystem/domain/global／isolated MySQL／LINE delivery acceptance 仍為後續 gate；不以本次 decision identity 冒充 implementation PASS。

## 13. 2026-08-22 人工裁決：public coordination slice

最新人工核准 M3 public slice 進入 `approved / in-progress`：建立 typed
`/api/v1/matching-coordination/{case_no}` Query／Preview／Apply family，所有入口採既有
authenticated admin convention 並要求 `require_system_admin`；actor 由 server-side principal
推導，client 不得提交 actor identity。Query／Preview 必須 zero-write，Apply 只由單一 composition-owned
outer UoW 驗證 fresh owner facts、source／preview fingerprint、idempotency 後提交 typed intent／reference；
不得直接寫 Orders、Assignment、Leave、Payroll root facts、呼叫 LINE/provider 或建立 schema／DB change。

Public results 必須使用既有 typed result／receipt；leave-impact 與 service-date-rematch 必須暴露專用
typed preview result（availability confirmation 或 reassignment reference），不得在 route 重算日期公式或
擴張 owner business rule。M3 overall 仍為 `PARTIAL / NOT_READY`，直到 route、schemas、dependencies、
composition wiring 與 focused public-contract tests 實際落地並通過。

**Approved exact write set（public slice）**

- `api/routes/matching_coordination.py`
- `api/schemas/matching_coordination.py`
- `api/dependencies/matching_coordination.py`
- `api/main.py`
- `tests/test_matching_coordination_public_contract.py`

Concrete facts adapters 若需新增 path，必須重用現有 approved query／repository paths，先取得 owner
確認，不得藉 public slice 擴張 owner、新增 root writer 或建立 public API 以外的 persistence surface。

## 14. 2026-08-22 人工裁決：Phase E／public production-completion successor

最新人工裁決採用經 anti-drift 修正的方案 A，核准建立 M3-owned additive persistence、唯讀
13-source facts adapter、repository／single outer Unit of Work，以及完整 public Query／Preview／Apply
composition。這項裁決只補齊本文件既有 Phase E 與 public slice 的 durable evidence 缺口，不改變
Scheduling Matching Coordination 的 owner、SSOT、跨域結果或 Eraser M3 observable outcomes。

M3 persistence 只可保存 immutable criteria／package／candidate／decision／rematch lineage、完整
source-version tuple、apply replay receipt，以及提交給既有 LINE／Assignment owner 的 typed durable
intent／reference。不得建立 Orders、Assignment、Leave、Scheduling、Payroll 或 LINE provider 的
current-state 副本；不得直接寫入其 root facts、呼叫 provider，或把 customer accepted 投影為正式
assignment、contract completion、official service day 或 Payroll success。

13-source adapter 僅透過既有 typed owner query／repository boundary 讀取事實；每個來源必須回 canonical
identity、version 與 fingerprint，不適用者明確標 `not_consulted`，unavailable／partial／ambiguous 固定
fail closed。Apply 固定採本文件 5.3 的 lock order、fresh rebuild、fingerprint／policy／idempotency驗證，
並以同一 composition-owned transaction append lineage、typed intent/reference 與 immutable receipt；
repository／adapter 不得 hidden commit。

**Approved production-completion write set**

- `infrastructure/mysql/matching_coordination_facts_adapter.py`（new；唯讀 13-source typed projection）
- `infrastructure/mysql/matching_coordination_repository.py`（new；M3 lineage／receipt／intent persistence）
- `subsystems/scheduling/matching_coordination_application.py`（new；single outer UoW composition）
- `api/dependencies/matching_coordination.py`
- `api/routes/matching_coordination.py`
- `api/schemas/matching_coordination.py`
- `api/main.py`
- `tests/test_matching_coordination_facts_adapter.py`
- `tests/test_matching_coordination_application.py`
- `tests/test_matching_coordination_public_contract.py`

**Approved Phase E artifact write set**

- `db/schema_parts/PROV-20260822-matching-coordination-successor.sql`
- `db/migration_releases/PROV-20260822-matching-coordination-successor.release.json`
- `db/migration_releases/PROV-20260822-matching-coordination-successor.descriptors.json`
- canonical fresh assembly／release catalog integration（integration writer sole-owned）
- `tests/test_matching_coordination_schema_contract.py`
- disposable fresh／preserve qualification plan與receipts

Phase E classification 固定為 additive `schema-only`、0 system seed、0 business-row backfill、0 destructive、
0 provider send。只核准在 disposable MySQL 完成 fresh bootstrap 與 preserve-data candidate qualification；
不核准套用目前 DB、`union_db`、production DB、source replacement、`--switch`、deployment 或 provider call。
任何 owned object、descriptor、release chain、read-only plan、fresh／preserve evidence 未完整通過時，結論
固定為 `DB_CHANGE_NOT_READY`，public routes 不得用 memory／fake persistence 冒充 production-ready。

## 15. 2026-08-22 人工裁決：修正版方案 A owner-command saga

最新人工裁決採用修正版方案 A。第 14 節「只提交給 LINE／Assignment owner」不足以承載 Eraser M3
的 zero-candidate 與日期／請假分支；修正為 M3 可在同一 outer UoW 保存提交給既有 Orders／
Scheduling／Assignment／LINE owner 的 typed durable intent／reference，但仍不得直接寫入任一 owner
root、替 owner 計算日期／合約公式，或把 intent 當成 owner 已完成。

owner-command saga 必須逐階段等待 canonical receipt：zero-candidate 同意折衷時先提交 Orders terms
update intent，receipt 回讀後才重建 matching facts；只有 fresh candidate 仍 eligible 且 willing 時才可
提交 Assignment conversion。禁止在沒有 candidate identity／willingness 時預先建立 conversion。請假
defer／substitute 與 service-date shift 同理，以既有 Scheduling／Orders／Assignment receipt 為下一階段
前置；LINE 雙邊通知只可由 committed intent 交付，不得在 M3 transaction 呼叫 provider。disagree 固定
保留 awaiting matching，零 owner mutation intent。此修正不新增 Domain、owner、seed、backfill、
destructive、目前 DB apply 或 provider 權限。

## 16. 2026-08-22 人工裁決：owner fresh-lock 與 public route amendment

Current-byte audit 證明第 14 節假設的既有 owner query boundary 尚不足以實作第 5.3 節完整鎖序：
service-date current version／days、candidate pool lineage、case-scoped availability、profile values 與
incumbent assignment 缺少共用 borrowed connection 的 typed `FOR UPDATE` read surface。最新人工裁決
核准補齊這些 owner-owned read／lock interfaces；它們只回傳既有 root facts，不建立 command claim、
不寫 owner root、不 commit／rollback，也不得以 synthetic owner Apply request 冒充 fresh query。

M3 Apply 固定在同一 outer UoW 依序執行：M3 claim／root → Orders terms/date → staff mutex IDs ascending
→ candidate pool/package lineage → availability/profile/lifecycle/incumbent／optional receipt fresh read。任何
owner interface 缺失、鎖集合擴張、partial／ambiguous 或版本漂移均回 `matching_lock_set_stale` 並 rollback。
Snapshot／package 內嵌 tuple 固定表示建立當時的歷史來源；Query／Apply 另回傳 current fresh tuple。
兩者不同代表 stale／rematch evidence，不得強迫相等、覆寫歷史 tuple，或建立包含自身 fingerprint 的循環。

Public route identity 固定如下：

- `POST /api/v1/matching-coordination/{case_no}/query`：read-only；body 只帶 optional expected source tuple，
  actor／correlation 由 server boundary 供應；不得帶 reason／idempotency。
- `POST /api/v1/matching-coordination/{case_no}/preview/{operation}`：zero-write；operation 使用 closed enum。
- `POST /api/v1/matching-coordination/{case_no}/apply/{operation}`：mutation；必須帶 `Idempotency-Key`、
  `X-Correlation-ID`、reason、expected source tuple 與 operation-specific preview identity。

本 amendment 核准修改既有 M3 production-completion paths，以及為 typed borrowed read／lock 必要的
`infrastructure/mysql/service_date_confirmation_repository.py`、
`infrastructure/mysql/staff_matching_preference_repository.py`、
`infrastructure/mysql/staff_availability_repository.py`、
`infrastructure/mysql/assignment_plan_repository.py` 與 candidate-pool read adapter及 focused tests。
分類固定為 0 schema、0 seed、0 backfill、0 destructive、0 current DB apply、0 provider；owner、SSOT、
公式與 root writer 均不改變。

## 17. 2026-08-22 人工裁決：initial criteria snapshot bootstrap

最新人工裁決核准補齊「尚無 M3 criteria snapshot」的單一 bootstrap 缺口。Preview／Apply 只投影
Orders owner 已確認的 `confirmed_service_dates` 與既有 `planned_start_date`、`service_days`、
`service_hours_per_day`、`service_time`、`requires_cooking`；不得接受 client 自訂 criteria、重算
Orders 公式或複製其他 owner current state。未存在 current confirmed service-date version 或日期集合時
固定 fail closed。

Preview 為 zero-write；Apply 必須帶 expected source tuple、preview fingerprint、reason、
`Idempotency-Key` 與 `X-Correlation-ID`，由 server principal 推導 actor。Apply 在既有 M3 single outer
UoW 先鎖 M3 root，再以 borrowed connection 鎖 Orders terms／confirmed service dates，fresh rebuild
同一 deterministic immutable snapshot，最後 append snapshot event／receipt 並單次 commit。其餘十一個
來源在 initial snapshot 明確記為 `not_consulted`；無 owner intent、outbox 或 provider side effect。

Public identity 固定為：

- `POST /api/v1/matching-coordination/{case_no}/preview/initial-criteria`
- `POST /api/v1/matching-coordination/{case_no}/apply/initial-criteria`

本 amendment 的 exact write set 為：

- `domains/scheduling/matching_coordination.py`（只重用既有 builder；不需變更）
- `subsystems/scheduling/matching_coordination_contracts.py`
- `subsystems/scheduling/matching_coordination_workflow.py`
- `subsystems/scheduling/matching_coordination_application.py`
- `infrastructure/mysql/matching_coordination_facts_adapter.py`
- `infrastructure/mysql/matching_coordination_repository.py`
- `infrastructure/mysql/order_terms_read_model.py`
- `infrastructure/mysql/order_terms_repository.py`
- `infrastructure/mysql/service_date_confirmation_repository.py`
- `api/dependencies/matching_coordination.py`
- `api/routes/matching_coordination.py`
- `api/schemas/matching_coordination.py`
- `api/main.py`
- matching coordination focused tests

分類固定為 0 schema、0 seed、0 backfill、0 destructive、0 current DB apply、0 provider、0 deployment；
不代表 M3 其他 Eraser／正式規格 branches 已完成。

## 18. 2026-08-22 current-byte Query composition receipt

本次依第 14、16、17 節的小切片執行，已把 Orders terms／confirmed service dates、M3 criteria
snapshot／package、candidate pool、incumbent assignment、staff profile／lifecycle、case-scoped
availability 與 effective generation 的既有 typed owner reads 接入同一 request-scoped composition；新增的
candidate-pool adapter 借用既有 connection，不 commit／rollback／close。Profile value 只使用 Domain
`parse_preference_value`，availability 只以 Orders owner 已確認日期呼叫既有 `load_matching_facts`，不重算
日期或改 owner root。

`POST /api/v1/matching-coordination/{case_no}/query` 已落地：body 只允許 optional expected source tuple，
actor／correlation 由 server boundary 供應，沒有 reason／idempotency，且只呼叫 application Query。Current
focused evidence為 `28 passed`（public contract、route、13-source facts），owner adapter相關 focused suites另有
`26 passed`；pytest cache permission warning不影響 assertions。

尚未暴露其他 public operation。Current workflow 的 matching-package／rematch preview 會忽略 request identity
而回既有 package；criteria-diff 尚未從 persistence 回讀完整 historical snapshots／refusal lineage；
zero-candidate 仍固定 generic manual alternative。正式規格只凍結單人全覆蓋優先及 2–4 連續無重疊 fallback，
尚未裁決 candidate ranking、segment combination policy 與可放寬的 soft-criteria policy。這些 business
policy 未裁決前不得由 adapter／route 自行發明，故 M3 overall維持 `PARTIAL / NOT_READY`。

本節為 0 schema、0 seed、0 backfill、0 destructive、0 current DB apply、0 provider。M3 schema artifacts
雖已依第 14 節取得 disposable qualification authority，仍未獲准套用 current DB；因此 real API workflow
為 `NOT_RUN`，不得以 route-level TestClient evidence宣稱 DB/API E2E PASS。

## 19. 2026-08-22 人工選擇 policy 裁決與 Preview 實作 receipt

最新人工裁決取代第 18 節末段的三項 policy blocker：candidate list 只依 `staff_name` 穩定排序，沒有推薦
分數或 server-side ranking；matching segments 由工會人員明確組合；zero-candidate 要放寬的 criteria 也由
工會人員明確選擇。這些裁決不改 owner boundary：Preview 仍不得寫 Orders、Assignment、Scheduling root
或呼叫 provider。

`POST /api/v1/matching-coordination/{case_no}/preview/package` 現在要求 1–4 個 explicit segments。Domain
驗證 selected staff 位於 current candidate pool、狀態為 eligible＋willing、每段日期落在該 staff 的
coverage evidence，且所有 segments 依 sequence 完整守恆 required service dates；單人為 single，2–4 人為
multi-segment。候選 view 依姓名、staff id、candidate id 穩定排序，空姓名排最後。Server 不替工會挑選或
重排組合。

`POST /api/v1/matching-coordination/{case_no}/preview/zero-candidate` 要求 explicit `relaxed_criteria`、policy
id/version，並只接受 current immutable criteria snapshot 內的欄位；未選、未知欄位或當前仍有
eligible＋willing candidate 固定 fail closed。未被選取的 criteria 投影為 unchanged hard criteria，choice 與
source tuple 共同進入 fingerprint；Preview 不會自動更新訂單或建立派案。

Current final-state focused evidence：matching Domain／workflow／application／query／facts adapter／repository／
public schema／routes 共 `103 passed`。另有 strict AST/import PASS；pytest cache permission warning不影響
assertions。實作為 0 schema、0 seed、0 backfill、0 destructive、0 current DB apply、0 provider；real DB/API
E2E仍為 `NOT_RUN`，M3 overall仍是 `PARTIAL / NOT_READY`，不得解讀為四條 Eraser business flow 已全部閉合。

## 20. 2026-08-22 criteria snapshot history 小包 receipt

M3 repository 現已由既有 `matching_coordination_criteria_snapshots` immutable table 依
`criteria_version ASC` 完整回讀歷史快照，facts adapter 只接受非空、版本唯一遞增、case identity一致，且
最後一筆精確等於 current snapshot 的 lineage；缺漏、亂序、identity歧義或 stale history 固定 fail closed。
此小包不新增 schema、事件或推論規則。

現有 candidate-contact `willingness_changed` payload 只保存 willingness 與文字 reason，沒有正式規格要求的
`affected_criteria`、`originally_willing`、`pain_resolved`，因此仍不能忠實重建 refusal history 的 G1／G2／G3
路由。本包不以 current reason 假造歷史，也不暴露 criteria-diff public Preview；該 branch 維持 blocked，須由
後續獨立小包先裁決持久化來源與 migration scope。

Focused evidence：全部 `test_matching_coordination_*.py` 共 `132 passed`；pytest cache permission warning不影響
assertions。分類為 0 schema、0 seed、0 backfill、0 destructive、0 current DB apply、0 provider；M3 overall仍為
`PARTIAL / NOT_READY`。

## 21. 2026-08-22 人工裁決：candidate／willingness／recontact lineage normalization

最新人工裁決核准修改 M3 原有 candidate／willingness／recontact 狀態與事件契約，以回答 criteria 修改後
「哪些人受到影響」。受影響人員由 Scheduling Matching Coordination 判斷；LINE Delivery 只接收 committed
exact recipient intents 並管理 pending／processing／sent／retry／failed，不新增 LINE 總狀態機，也不得從
訊息文字反推候選人。

Willingness 狀態固定為：

```text
unconfirmed → pending → willing | unwilling(reason_code) | expired
willing | unwilling | expired → stale（criteria snapshot 改變）
stale → recontact_previewed → recontact_queued → pending
stale → silent_excluded（與本次 diff 無關）
```

每筆 M3 immutable willingness event 必須保存 `event_id`、candidate／staff identity、criteria snapshot、
完整 source-version tuple、previous/current state、stable reason code 與 `affected_criteria`。`willing` 表示確認
整份 snapshot，affected criteria 由 server 固定為該 snapshot 全部 keys；`unwilling` 必須有 closed stable
reason code 與 non-empty、屬於該 snapshot 的 affected criteria。free-form command reason 只作 audit，不得充當
stable reason。既有 candidate-contact free-text event 不 backfill、不猜測；缺完整 lineage 時 criteria-diff
Preview 固定 fail closed／manual review。

Criteria diff 對 before-snapshot 最新 event 作 deterministic routing：current state=`willing` 且 affected keys
與 diff 相交為 G1 reconfirm；current state=`unwilling`、affected keys 相交、fresh candidate 已 eligible 且舊
reason 不再成立為 G2 reprobe；其餘為 G3 silent exclude。只有 G1／G2 且具 current eligible recipient binding
的 candidate 可進 exact recipient intents。Preview 零寫入；Apply fresh-lock、重算同一 diff／route，保存 M3
event／receipt／LINE intent 後單次 commit；LINE provider 不在該 transaction 執行。

本 amendment 的 exact write set 限既有 M3 Domain／contracts／workflow／application、M3 MySQL repository／
facts adapter、matching coordination API schema／route、focused tests與本文件／四模組計畫。Line Delivery、
candidate-contact owner table、Orders／Assignment／Payroll root writer均不修改。持久化沿用已核准 M3
`matching_coordination_events.event_payload` JSON；0 SQL schema、0 seed、0 backfill、0 destructive、0 current
DB apply、0 provider、0 deployment。狀態為 `approved / in-progress`。

### 21.1 2026-08-23 current-byte implementation receipt

Willingness closed enum、immutable event identity/source/snapshot binding、G1／G2／G3 deterministic routing、
exact recontact intent payload／receipt round-trip、locked fresh-read與package fingerprint/digest tamper檢查已落地。
Public Query、initial criteria、package、criteria-diff、zero-candidate、rematch、caregiver-selection與
customer-decision routes已有focused contract evidence；service-date-rematch Preview亦已保存完整
assignment／staff／original／shifted date identity，並以borrowed connection唯讀核對confirmed dates、
incumbent assignment與shifted-date availability。全部`test_matching_coordination_*.py`目前為`154 passed`。

Leave-impact typed preview核心已存在，但production composition尚未接入canonical Scheduling leave receipt
owner port；generic Preview只回package view，generic Apply只回`rematch_required` receipt，不能冒充
leave resolution閉環。Service-date Preview已閉合，但Apply仍缺不隱含建立aggregate的owner fresh-lock read，
且owner-command receipt saga未閉合；因此維持fail closed。這些缺口維持
`in-progress`；本receipt不新增schema、DB操作、provider呼叫或owner root writer，M3 overall仍為
`partial / NOT_READY`。

---
doc_type: evidence-matrix-draft
declared_status: draft
identity: PROV-20260817-react-admin-scheduling-query-page-slice-evidence-matrix
date: 2026-08-17
owner: Scheduling React Page Integration Owner
scope: query-only SchedulingPage calendar page-slice
authority: PROV-20260817-react-admin-scheduling-query-page-slice-work-package.md
not_a_receipt: true
---

# Scheduling query page-slice evidence matrix（草案）

本文件是執行前盤點草案，不是契約 freeze、測試回執、browser receipt 或人工核准。欄位若與 live Pydantic、Global error
boundary 或最新人工裁決不一致，必須在實作前標記 `live-drift` 並更新 final matrix；不得用本草案授權 code、DB 或 mutation。

## 1. Endpoint／field matrix

| Source／endpoint | Public field | Current typed source | Required／nullable disposition | React slot／處置 | Notes／驗證 |
|---|---|---|---|---|---|
| `GET /api/v1/staff/summaries` | `success` | `BaseResponse` | success response required；不以 frontend default 補值 | client envelope | route/auth/error需確認 |
| 同上 | `message` | `BaseResponse` | required string on success | 不直接當 business state | 不依中文 message 分支 |
| 同上 | `data.items[].id` | `StaffSummaryView.id` | required positive integer | `scheduling.calendar.staff-select`, row identity | duplicate id fail closed |
| 同上 | `data.items[].name` | `StaffSummaryView.name` | nullable string | selector label；null→`月嫂 #id` | 不猜姓名 |
| 同上 | `data.items[].phone` | `StaffSummaryView.phone` | nullable string | 不 render／不送入 calendar view | PII minimization |
| 同上 | `data.next_cursor` | `StaffSummaryPageView.next_cursor` | nullable positive integer | next staff page control | cursor must advance |
| `GET /api/v1/scheduling/staff/{staff_id}/current-calendar` | `data.staff_id` | `SchedulingCurrentProjectionView.staff_id` | required positive integer | loaded row identity | must match requested staff |
| 同上 | `data.range_start` | `SchedulingCurrentProjectionView.range_start` | required date | calendar header／query echo | range mismatch fail closed |
| 同上 | `data.range_end` | `SchedulingCurrentProjectionView.range_end` | required date | calendar header／query echo | max 62 days server bound |
| 同上 | `data.evaluated_at` | `SchedulingCurrentProjectionView.evaluated_at` | required datetime | projection timestamp | server value only |
| 同上 | `data.assignments[]` | `SchedulingCurrentAssignmentView` | required array; nested extra forbidden | optional read-only assignment detail／bar metadata | no local lifecycle/date derivation |
| 同上 | `assignments[].assignment_id` | same | required positive integer | stable row/bar identity | no `Date.now()` |
| 同上 | `assignments[].case_no` | same | nullable string | case label | client name unavailable |
| 同上 | `assignments[].generation_id` | same | required positive integer | lineage metadata, not business logic | not editable |
| 同上 | `assignments[].scheduling_version` | same | required nonnegative integer | version metadata | no Apply |
| 同上 | `assignments[].staff_id` | same | required positive integer | ownership check | must equal selected staff |
| 同上 | `assignments[].status` | `AssignmentLifecycleStatus` | required closed enum | server lifecycle pill | no order-status mapping |
| 同上 | `assignments[].assigned_start_date/end_date` | same | required dates | server-provided range display | no date extension calculation |
| 同上 | `assignments[].first_service_at/completion_at` | same | required datetime | optional read-only details | never rewrite status |
| 同上 | `assignments[].official_service_day_count` | same | required positive integer | read-only count | no count recomputation |
| 同上 | `assignments[].actual_hours` | same | required positive integer | read-only hours | no payroll meaning |
| 同上 | `data.days[]` | `SchedulingCurrentDayView` | required array; duplicate dates fail closed | calendar columns | source of rendered dates |
| 同上 | `days[].calendar_date` | same | required date | day header/cell key | no fixed month sample |
| 同上 | `days[].available` | same | required boolean | server availability display only | absence ≠ eligibility |
| 同上 | `days[].entries[]` | `SchedulingCurrentDayEntryView` | required array; nested extra forbidden | occupancy label(s) | no local occupancy inference |
| 同上 | `entries[].occupancy_kind` | `SchedulingOccupancyKind` | required closed enum | legend/status mapping | exact server enum only |
| 同上 | `entries[].case_no` | same | nullable string | case label | no client PII |
| 同上 | `entries[].assignment_id/lock_id/segment_id/availability_block_id` | same | nullable positive integer | stable lineage/detail | no mutation affordance |
| 同上 | `entries[].assignment_status` | same | nullable closed enum | server status display | no mapping from order status |
| 同上 | `entries[].unavailability_kind` | same | nullable string | typed/unavailable label | no kind invention |
| 同上 | `data.case_versions[]` | `SchedulingCaseVersionView` | required array; strict nested | version metadata / evidence | not Apply permission |
| 同上 | `data.projection_token` | `SchedulingCurrentProjectionView` | required 64-lowercase-hex | lineage test evidence only | do not display as business status |
| HTTP error | `detail.error` | `SchedulingCurrentTypedErrorView`／Global envelope | required typed category/code/correlation; optional lists only per public contract | page error/retry/unavailable | no raw `HTTPException` text |

## 2. UI slot disposition

| Existing surface | Current source | Target disposition | Completion evidence |
|---|---|---|---|
| staff list／Gantt rows | `MOCK_STAFF` | `wired` from bounded staff summaries + current-calendar GET | Network→DOM, loaded count |
| calendar day grid | fixed August 2026 + local `Date` | `wired` from `projection.days` | server range/date sentinel |
| actual assignment bars | hardcoded staff/order branches | `wired` only from assignment/day entries | no literal staff/order scan |
| buffer／waiting／unavailability legend | local labels | `wired` from closed occupancy enum | enum mapping test |
| client name/address/phone | mock order facts | `unavailable`（current projection does not provide them） | explicit slot text |
| ghost projection／prospective order | `PROSPECTIVE_ORDERS` | `unavailable` + lock control disabled | zero matching non-GET |
| precision／shift extension Drawer | local date math and alert | `unavailable` + save/add/remove controls disabled | zero fake mutation |
| leave/substitution tab | local `inServiceLeaveRecords` | `unavailable`；layout retained | no mock rows |
| holiday tab | local `holidays` | `unavailable`；all CRUD controls disabled | no holiday GET in this slice |
| leave inbox tab | local leave records | `unavailable`；accept/reject disabled | no prompt/alert |
| search/filter | local staff literal status | `wired` only over loaded server rows; scope label required | request budget test |
| deep link `#scheduling` | shell route | `wired` with auth guard and reload state | browser reload receipt |

## 3. Failure／state evidence matrix

| Scenario | API evidence | UI expected | Status before execution |
|---|---|---|---|
| No memory session | 0 GET | shell login／unavailable | `required` |
| Staff summary empty | typed 200 empty page | empty selector state; no calendar GET | `required` |
| Calendar empty range | typed 200 with empty days/assignments | explicit empty, not “可接案” | `required` |
| 401／403 | typed auth error | login／permission unavailable | `required` |
| 404 staff | `staff_not_found` | row-level not found, no first-row fallback | `required` |
| 409／422 | typed conflict/validation | error code + correlation, retry only if safe | `required` |
| 503／timeout/network | typed unavailable or transport error | retryable error, no fake empty | `required` |
| Range/staff switch during request | AbortSignal + generation | stale response discarded | `required` |
| Duplicate staff/day/extra field | strict decoder failure | schema error/unavailable | `required` |
| Existing DB UI observation | GET only | server values visible in Chrome | `required if runtime available`; otherwise blocked |

## 4. Forbidden evidence substitutions

- Vitest／Happy DOM、mock fixture、HTTP 200、舊 Streamlit screenshot或現有 DB final state不能單獨證明 real browser query。
- UI 顯示資料不能證明 mutation、transaction、replay、DB engine、entry cutover或Streamlit retirement。
- `MOCK_STAFF`、`MOCK_ORDERS`、固定 August 2026、`alert/confirm/prompt`、非 GET、前端日期／buffer／coverage推導都不能出現在 final implementation。

## 5. Finalization rule

執行開始前由 Integration Owner 將本草案依 live code／Pydantic／Global error evidence 凍結為 final `contract-field-matrix.md`；
只有 final matrix、focused tests、build/lint、write-set audit與真瀏覽器 GET evidence 全部適用項目通過，才可標
`query-real-data-validated`。本草案不更新任何 shared index，也不構成核准。

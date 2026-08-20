---
doc_type: evidence-inventory
declared_status: active
date: 2026-08-17
owner: React Migration Integration Owner
scope: Phase 3 scenario adoption and missing-artifact gates
authority: evidence-only
---

# Phase 3 Scenario Lineage Matrix

本表只記錄Phase 3的既有Scenario adoption、successor contract與缺少artifacts；不構成
production、DB、provider、browser mutation或工作包核准。

## 1. Canonical gate

1. 每個WP必須裁決`ADOPT`、`SUPPLEMENT`、`TEST_DATA_GAP`、`BLOCKED_UPSTREAM`或
   `BLOCKED_DECISION`。
2. 開工前必須能從source scenario追到successor scenario、fixture、expected、applicable
   DB/API/UI oracle與fresh receipt。
3. component fixture、writer mock、screenshot、Happy-DOM或舊evidence不能取代controlled business data。
4. `validation/ui_business_workflows/` 已建立 Part 04、Part 09、Part 14 的 metadata-only
   checklist；所有需browser的Phase 3 WP在真實 runtime receipt產生前仍固定`TEST_DATA_GAP`。
5. Data Browser尚無正式Part identity；不得由page writer自行分類。

## 2. Lineage inventory

| WP family | Existing canonical source | Disposition | Required successor artifacts | Current gate |
|---|---|---|---|---|
| Global FastAPI error boundary | `GERR-TIMEOUT-001`, `GERR-TYPED-UI-RETRY-002`, `AC-CAPABILITY-SESSION-002` | `ADOPT_AND_SUPPLEMENT` | `global_fastapi_typed_error_boundary.json`, strict expected/error snapshots, TestClient receipt | `TEST_DATA_GAP` |
| 3A Customer Service / Identity | `LINE-IDENTITY-DELIVERY-001`, `LINE-IDENTITY-DELIVERY-002`, `AC-CAPABILITY-SESSION-002` | `ADOPT_AND_SUPPLEMENT` | controlled ticket/binding identities, Part 15 checklist, fresh TOTP browser receipt | `BLOCKED_UPSTREAM` |
| 3B1 Staff | `SCH-ASSIGNMENT-COVERAGE-001`, `AC-CAPABILITY-SESSION-002` | `SUPPLEMENT` | `react_admin_staff_safe_actions.json`, fixture/expected, Staff API/MySQL/UI receipt, Part 04 checklist | `TEST_DATA_GAP` |
| 3B-Q-H / Q-R Current Calendar | `SCH-ASSIGNMENT-COVERAGE-001`, `AC-CAPABILITY-SESSION-002`, `GERR-TIMEOUT-001` | `SUPPLEMENT` | `react_admin_scheduling_current_query.json`, current-calendar success/empty/error/abort oracle, Part 09 checklist/browser receipt | `TEST_DATA_GAP` |
| 3B2 Leave / Substitution | `SCH-ASSIGNMENT-COVERAGE-001`, `PAY-ASSIGNMENT-RECONCILIATION-002`, `GDATA-CROSS-DOMAIN-001` | `ADOPT_AND_SUPPLEMENT` | `react_admin_leave_substitution.json`, outer-UoW/linked-request/LINE-intent expected, disposable MySQL/API/UI receipts | `BLOCKED_UPSTREAM` |
| 3B-H Holiday | `SCH-ASSIGNMENT-COVERAGE-001`; cache-only supplement `CACHE-READ-PROJECTION-002` | `SUPPLEMENT` | `react_admin_holiday_policy.json`, horizon/version/source fixture, zero-write/cache/oracle, Part 09 checklist/browser receipt | `TEST_DATA_GAP` |
| 3C Access Audit | `AC-SECURITY-STATE-001`, `AC-CAPABILITY-SESSION-002` | `SUPPLEMENT` | `react_admin_access_audit_query.json`, masked expected, browser receipt | `TEST_DATA_GAP` |
| 3C Durable Jobs | `JOB-DURABLE-001`, `JOB-QUEUE-LIFECYCLE-002`, `GERR-TYPED-UI-RETRY-002` | `BLOCKED_UPSTREAM` | Durable Job persistence decision PASS, `durable_job_public_outcome.json`, receipt/terminal observation | `BLOCKED_UPSTREAM` |
| 3D Anomaly detail | `ANOM-PROJECTOR-CLOSED-LOOP-003`, `ANOM-SCHEDULING-CLOSED-LOOP-002`, `ANOM-CLOSED-LOOP-001` | `ADOPT_AND_SUPPLEMENT` | typed detail/timeline/recovery/redaction oracle, Part 14 checklist, Phase2D-H engine receipt | `BLOCKED_UPSTREAM` |
| 3D Warning transition | `CI-CASE-IMPORT-001`, `FI-CANONICAL-STAGING-003`, `FI-STAGING-DEDUP-002` | `SUPPLEMENT` | `react_admin_import_warning_transition.json`, before/after/replay/receipt/re-query oracle | `BLOCKED_UPSTREAM` |
| 3D Claim / Resolve | `ANOM-*` 僅可提供查詢facts | `BLOCKED_DECISION` | 先裁決Preview policy，再建exact mutation scenario/WP | `BLOCKED_DECISION` |
| 3D Data Browser Query | none sufficient | `TEST_DATA_GAP` | allowlist/masking/cursor/PII rejection scenario, fixture/expected/MySQL/API/browser receipt；`PROV-20260817-react-admin-phase3d-data-browser-part-identity-gap`裁決Part owner | `TEST_DATA_GAP`＋`BLOCKED_DECISION` |
| 3D Source Correction | none applicable | `BLOCKED_DECISION` | retire generic correction or owning-domain successor decision | `BLOCKED_DECISION` |
| 3E Orders gaps | existing Orders scenarios are insufficient for formal recommendation/timeline/three settlements/create entry | `BLOCKED_DECISION` | each owner/public contract decision and dedicated successor scenario | `BLOCKED_DECISION` |

## 3. Canonical successor paths

Machine-readable routing manifest：

- `validation/catalog/phase3_scenario_lineage.json`；固定八個semantic scenario identities、dependency DAG、
  source→successor mapping、oracle applicability與future receipt requirements。不得由目錄discovery自產
  expected set。

Scenario contracts（revision 1；metadata-only，尚無runtime PASS）：

- `validation/scenarios/global_fastapi_typed_error_boundary.json`
- `validation/scenarios/react_admin_staff_safe_actions.json`
- `validation/scenarios/react_admin_scheduling_current_query.json`
- `validation/scenarios/react_admin_leave_substitution.json`
- `validation/scenarios/react_admin_holiday_policy.json`
- `validation/scenarios/react_admin_access_audit_query.json`
- `validation/scenarios/react_admin_import_warning_transition.json`
- `validation/scenarios/react_admin_data_browser_query.json`

去敏input/expected：

- `validation/fixtures/phase3/`（每份含data classification、generation、allowed use與redaction metadata）
- `validation/expected/phase3/`（只保存DB/API/UI/replay/recovery oracle）

UI checklist：

- `validation/ui_business_workflows/README.md`
- `validation/ui_business_workflows/checklist_manifest.yaml`
- `validation/ui_business_workflows/part_04_staff_matching/`
- `validation/ui_business_workflows/part_09_scheduling/`
- `validation/ui_business_workflows/part_14_anomalies/`
- Data Browser等待`PROV-20260817-react-admin-phase3d-data-browser-part-identity-gap`裁決，不建立臨時目錄。

Runtime receipts只能由不同驗證者產生於`validation/receipts/phase3/`或對應正式
evidence directory；本包只登錄`missing | not_run | blocked` identity，writer不得預填PASS。

Scenario identities固定為：`GERR-REACT-ADMIN-TYPED-BOUNDARY`、
`SCH-REACT-ADMIN-STAFF-SAFE-ACTIONS`、`SCH-REACT-ADMIN-CURRENT-QUERY`、
`SCH-REACT-ADMIN-LEAVE-SUBSTITUTION`、`SCH-REACT-ADMIN-HOLIDAY-POLICY`、
`AC-REACT-ADMIN-AUDIT-QUERY`、`ANOM-REACT-ADMIN-WARNING-TRANSITION`、
`GDATA-REACT-ADMIN-DATA-BROWSER-QUERY`；revision皆為1。Data Browser仍保持`BLOCKED_DECISION`。

## 4. Shared-page serial order

- `StaffPage.tsx/.css`：只由3B1單一Presentation writer。
- `SchedulingPage.tsx/.css`：3B-Q-R → 3B2-R → 3B-H-R，每波fresh-read前一波diff/tests。
- `AnomaliesPage.tsx/.css`：3D-R detail → future Warning mutation → future Claim/Resolve；
  尚未核准的controls native disabled。

## 5. Mechanical acceptance

- strict decode所有successor JSON/YAML，scenario ID/path不重複，source refs存在。
- fixture不含真實phone、LINE ID、bank、token、secret、credential。
- expected分開DB/API/UI oracle與N/A/blocked理由，不可只列row count。
- browser receipt記錄scenario revision、controlled identity、auth flow、Network→DOM與re-query；截圖不是
  唯一evidence。
- 任一required artifact缺少固定`PHASE3_SCENARIO_LINEAGE_NOT_READY`。

## 6. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | evidence inventory only |
| Change Inventory | PASS | 0 DB write |
| Static Release | NOT_RUN | not applicable |
| Descriptor | NOT_RUN | not applicable |
| Read-only Plan | NOT_RUN | not applicable |
| Engine Verification | NOT_RUN | future scenario WPs |
| Developer Acceptance | NOT_RUN | no existing DB operation |

結論：`DB_CHANGE_NOT_READY`。

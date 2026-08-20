---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-anomalies-query-page-slice
date: 2026-08-17
owner: Anomalies React Page Integration Owner
domain: Anomalies
subsystem: anomaly-summary-query / import-warning-query / React Presentation
initiative: react-admin-migration
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
prerequisites: PROV-20260817-react-admin-page-slice-migration-execution-decision approved; Phase 2D-H public query evidence available; Phase 2C volatile bearer session available
approval_required: 核准此 exact React Anomalies Query Page-Slice Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-anomalies-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: page/client/schema/adapter/auth drift requires fresh read and re-freeze; never overwrite user baseline
---

# Phase 3：Anomalies query page-slice 真實資料與 Drawer GET 接線工作包

> Activation：使用者已明確回覆「核准此 exact React Anomalies Query Page-Slice Work Package」。

> Completion：React focused 78、full React 517 tests與build通過；真Chrome list/tasks/detail/referral GET
> 均200並進DOM，Claim／Resolve／Recovery／transition維持disabled且0 non-GET。狀態為`completed`。

## 0. 目的與最小完成邊界

本包依已採用的逐頁精簡遷移裁決，將既有 `#anomalies` React 頁面的兩個現有唯讀清單維持
real-data 接線，並在既有 Drawer 原位置補上兩個已存在的 GET 查詢：

1. `GET /api/v1/anomalies`：anomaly summary list，固定 `include_snapshot=false`。
2. `GET /api/v1/import-warning-tracking/tasks`：field-level import warning task list。
3. `GET /api/v1/anomalies/{fingerprint}`：選取 anomaly 後 lazy query typed detail envelope。
4. `GET /api/v1/import-warning-tracking/tasks/{occurrence_identity}/referral?expected_version=N`：選取 warning 後 lazy query owning referral。

Drawer 只在使用者明確開啟時查詢 detail/referral；不得在清單載入時 N+1 預取。現有 KPI、category/status
filter、cards、Import Warning 區塊、Drawer 與 CSS 層級必須保留。沒有封閉 typed 欄位的 detail/timeline/
recovery/action slot 在原位置顯示 unavailable，不以 raw payload、mock 或前端推導補齊。

本包不是 Anomalies domain 完成、不是 mutation、不是 entry cutover，也不是 Streamlit retirement。
完成上限固定為 `query-real-data-validated`。

## 1. 明確排除與安全不變量

- 只允許上列四個 GET；不呼叫 `/api/v1/anomaly-recovery/**`，不呼叫任何 action/scan/retry route。
- `anomalies.card.claim`、`anomalies.drawer.resolve-reason`、`anomalies.drawer.resolve` 保留原位置、native `disabled`，不得有 handler。
- Import Warning transition／override、owner repair、recovery apply、projector retry、claim、resolve 均 deferred；不新增表單成功狀態。
- React 不改 DB、schema、migration、seed、backfill、production data、Streamlit source、entry registry 或 shared transport/Auth。
- 既有 DB 僅能供人工真 Chrome GET UI 觀察；不得 INSERT／UPDATE／DELETE、seed、migration、repair 或建立測試資料。
- generic anomaly `workflow_status` 與 import-warning `tracking_status` 是兩套狀態機，不得合併 KPI、badge 或 transition。
- `source_identity`、fingerprint、raw snapshot、timeline、source binding 與完整個資不可進一般文案、log 或 receipt。
- 只有 server response 能提供業務事實；client/adapter 不推導 root cause、claimability、repairability、resolved meaning、日期、金額或 blocker。

## 2. 現況契約輸入（唯讀，不是本包 backend write set）

### 2.1 Existing list contracts

| Endpoint | Current route/schema | Allowed query | Success view |
|---|---|---|---|
| `GET /api/v1/anomalies` | `api/routes/anomaly_registry.py::query_anomalies`; `api/schemas/anomaly_registry.py::AnomalySummaryView` | `active_only`、`limit 1..200`、`offset >= 0`、client 固定 `include_snapshot=false` | `BaseResponse[list[AnomalySummaryView]]`; severity `warning|blocking`; workflow `open|claimed|resolved`; `display_snapshot` must be null/unavailable |
| `GET /api/v1/import-warning-tracking/tasks` | `api/routes/import_warning_tracking.py::query_tasks`; `api/schemas/import_warning_tracking.py::ImportWarningTaskView` | `active_only`、`limit 1..200`、`offset >= 0` | `BaseResponse[list[ImportWarningTaskView]]`; six tracking statuses; five allowlisted navigation actions or null |

### 2.2 Drawer GET contracts

| Endpoint | Current route/schema | UI use | Raw/unavailable boundary |
|---|---|---|---|
| `GET /api/v1/anomalies/{fingerprint}` | `query_anomaly_detail`; `AnomalyDetailView` | lazy refresh of selected summary and safe detail metadata | `display_snapshot`/timeline/source bindings are not renderer input; any field without closed typed shape stays unavailable |
| `GET /api/v1/import-warning-tracking/tasks/{occurrence_identity}/referral?expected_version=N` | `query_referral`; `WarningReferralView` | lazy warning Drawer owner referral and neutral `#data-import` navigation | only declared referral fields are renderable; no corrected payload, source snapshot or transition result |

The Phase 2D-H matrix and receipts remain the evidence for existing enum/auth/query behaviour:
[`contract-matrix.md`](../03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening/contract-matrix.md)、
[`closure-gate-verification-receipt.md`](../03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening/closure-gate-verification-receipt.md)。
本包不新增欄位 gap 文件；實作時若現況與上述 contract 不一致，標記 live-drift 並停止該欄位，不放寬 decoder。

## 3. UI surface disposition and stable IDs

### 3.1 Wired query surfaces

| Surface / identity | Source | Behaviour |
|---|---|---|
| `anomalies.page`, `anomalies.kpis` | anomaly list | preserve shell and loaded-scope KPI |
| `anomalies.category-filters`, `anomalies.status-filters` | local list state | filter only loaded summaries; zero GET |
| `anomalies.card.<fingerprint>` | summary fingerprint | stable server identity; fingerprint is not rendered as business text |
| `anomalies.card.drawer_open` | selected summary | open Drawer; one lazy detail/referral GET only as applicable |
| `anomalies.drawer` | detail/referral response | render safe scalar fields; independent loading/error/empty/unavailable slots |
| `anomalies.drawer.detail`, `anomalies.drawer.timeline`, `anomalies.drawer.evidence` | detail GET | only closed typed fields; raw/untyped content unavailable |
| `anomalies.drawer.referral` | warning referral GET | declared owning lane/code/field/masked subject/message/action only |
| `anomalies.import-warnings` | warning task list | keep field-level occurrence identity and separate tracking status |
| `anomalies.navigation.data-import` | allowlisted navigation action | hash-only `#data-import`; no mutation |

### 3.2 Locked/deferred controls

| Stable control | Required state |
|---|---|
| `anomalies.card.claim` | native `disabled`; zero request |
| `anomalies.drawer.resolve-reason` | native `disabled`; no writable local value |
| `anomalies.drawer.resolve` | native `disabled`; zero request |
| warning transition/override controls, if present | native `disabled`; no POST/preview/apply |
| recovery/action/apply controls, if present | native `disabled` or explicit unavailable; no `/anomaly-recovery` calls |

## 4. Exact implementation write set (only after exact approval)

### React production

- `ui_react/src/api/anomalies/anomaly_query_schemas.ts`
- `ui_react/src/api/anomalies/anomaly_query_client.ts`
- `ui_react/src/api/anomalies/anomaly_query_errors.ts` (only if existing typed error mapping must cover the two GETs)
- `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`
- `ui_react/src/pages/AnomaliesPage.tsx`
- `ui_react/src/pages/AnomaliesPage.css`

### Focused tests and fixtures

- `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts`
- `ui_react/src/tests/anomaly_query_client.test.ts`
- `ui_react/src/tests/anomaly_query_adapter.test.ts`
- `ui_react/src/tests/anomalies_page_real_data.test.tsx`
- `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx`
- `ui_react/src/tests/anomalies_detail_referral_flow.test.tsx` (new)
- `ui_react/src/tests/anomalies_request_budget.test.tsx` (new)

### Evidence

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-anomalies-query-page-slice/`

Backend route/schema/test files listed in §2 are read-only contract inputs. No backend production or backend test
file is in this package's implementation write set. Do not modify `README.md`, the migration main plan, shared
transport/runtime decoder/Auth, package lock, DB artifacts, or other page slices in this work package.

## 5. Client, schema, adapter and page rules

1. Every request reads the current in-memory session token immediately; missing token means zero fetch and typed auth state.
2. Client methods are limited to the four GETs in §0. Caller cannot replace `Authorization`; every request accepts `AbortSignal` and timeout.
3. Zod schemas are strict and contract-specific. Required server keys remain required; nullable is not optional. No `z.any`, `z.unknown`, `z.record`, `.passthrough()`, `.catch()`, `.default()`, `.coerce()`, `.preprocess()`, `.transform()`, `as any` or `unknown as`.
4. Detail/referral schemas must reject missing required keys, wrong primitive, extra envelope/nested fields, invalid enum and null violations. Raw nested detail fields are either explicitly typed by live contract or rendered unavailable; never loosen with catch-all decoding.
5. Adapters are pure mapping/formatting only. They must preserve separate state machines, mask internal identities, preserve null, and produce explicit unavailable slots.
6. Page uses independent discriminated query states for anomaly list, warning list, selected detail and selected referral. Stale generations are aborted/discarded; closing/switching Drawer prevents stale response overwrite.
7. No background polling, prefetch, optimistic success, local mutation, `alert`/`confirm`/`prompt`, or fake toast.

## 6. Request budget and stale/abort policy

| User action | Allowed calls | Maximum |
|---|---|---:|
| page mount | anomaly list GET + warning task list GET | 1 each |
| retry one failed family | failed family GET only | 1 |
| local category/status filter | none | 0 |
| open anomaly Drawer | anomaly detail GET | 1 per fingerprint/generation |
| open warning referral | referral GET | 1 per occurrence/version/generation |
| close/switch Drawer | none; abort pending request | 0 |
| disabled claim/resolve/recovery/transition | none | 0 |
| hash navigation | hash only | 0 non-GET |

Repeated same-identity requests must not append duplicates or allow older responses to replace newer selection. A
`401/403/404/409/422/500/503`, timeout, network failure or abort remains a typed error/unavailable state; it must not
be converted to an empty successful list or fake detail.

## 7. Acceptance gates and evidence

| Gate | Required proof | Initial status |
|---|---|---|
| G0 Scope | exact approval, fresh dirty baseline, no out-of-write-set changes | `BLOCKED` until approval |
| G1 Matrix | live route/schema-to-Zod field matrix including four GETs, nullability, redaction, error/status | `NOT_RUN` |
| G2 Client | positive and adversarial strict decode tests, auth/header, allowlist, abort | `NOT_RUN` |
| G3 Adapter | sentinel DTOs change DOM-facing values; no root/status/date/action inference | `NOT_RUN` |
| G4 Presentation | independent query states, lazy Drawer, request budget, stale discard, unavailable slots | `NOT_RUN` |
| G5 Safety/static | 0 non-GET, disabled controls, no mock dependency, build/lint/Vitest/UTF-8/diff/secret scan | `NOT_RUN` |
| G6 Browser | real FastAPI + Vite + user-entered account/TOTP; Network↔DOM for existing DB GET only | `NOT_RUN` |

Only G0–G6 applicable query evidence may yield `query-real-data-validated`; never claim mutation-ready,
entry-readiness, cutover or retired. Existing DB browser evidence is not a DB engine/mutation receipt.

Required evidence directory files after implementation: `contract-field-matrix.md`,
`candidate-change-inventory.md`, `verification-receipt.md`, `browser-smoke-receipt.md`, `open-findings.md`.
The separate matrix draft in §8 is the only artifact created now and is not a PASS receipt.

## 8. DB gate (0 DB change)

| Gate | Status | Evidence / reason |
|---|---|---|
| Scope | `PASS` | query-only React page slice; no DB write set |
| Change inventory | `PASS` | no schema/seed/backfill/destructive artifact |
| Static release | `NOT_RUN` | no release change |
| Descriptor | `NOT_RUN` | no owned-object change |
| Read-only plan | `NOT_RUN` | no DB tooling; existing DB only browser GET |
| Engine verification | `NOT_RUN` | no new DB; UI observation is not engine evidence |
| Developer acceptance | `NOT_RUN` | no migration or existing DB mutation |

Conclusion: `DB_CHANGE_NOT_READY` by repository gate policy; this does not block query-only implementation after exact approval.

## 9. Rollback and successor routing

If the React query candidate fails, route `#anomalies` back to the existing Streamlit anomaly entry for display only;
do not rollback Domain data or call the old UI an operational mutation rollback. Claim/Resolve, warning transition,
recovery action, detail contract hardening, external provider, transaction, entry cutover and Streamlit retirement
remain separate successor packages.

---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-account-query-page-slice
date: 2026-08-17
owner: Account Page Query / React Integration Owner
domain: Access / Security Audit / Global Jobs Presentation
subsystem: account-directory-query / masked-audit-query / job-observation-query / React Presentation
initiative: react-admin-migration
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
prerequisites: approved page-slice execution decision; Phase 2C account→TOTP bearer session completed
approval_required: 核准此 exact React Account Query Page-Slice Work Package
approval_evidence: user-replied-核准此-exact-React-Account-Query-Page-Slice-Work-Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-account-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: AccountManagementPage and each bounded route/schema/client require fresh read and sequential freeze before edits
---

# Phase 3：Account query page-slice 真實資料接線工作包

## 0. 單頁整合裁決

本包是 `AccountManagementPage.tsx` 的唯一 presentation writer，依序完成三個互不混用的唯讀區塊：

1. root-only account directory GET；
2. all-enabled-internal masked audit GET；
3. `system.administration` capability保護的safe job observation GET。

現有 Account Center、Access Audit React、Durable Job Observability React 等 proposed 文件保留歷史，不由本包
自行改寫；核准後由本 page-slice 串行承接其 **query presentation** 範圍。帳號 mutation、MFA enrollment/reset、
session revoke、job cancel/retry/run、raw audit/job outcome 均不被承接。

本包完成上限固定為 `query-real-data-validated`，不代表 Access mutation、Global durable outcome、entry cutover
或 Streamlit retirement 完成。

## 1. Current UI problems to remove

Current `AccountManagementPage` contains four fake users, fake email/IP/session/TOTP facts, four fake audit rows,
local enable/disable/revoke/create/TOTP mutations, a simulated QR/seed, fake job/DB/LINE health cards, `Date.now()`,
`alert()` and `confirm()` success paths. All are removed from the production dependency closure.

The four existing tabs and visual hierarchy remain:

- accounts;
- TOTP explanation/setup slot;
- audit;
- jobs。

Unavailable fields stay in place with explicit server-unavailable text; no mock or frontend derivation replaces them.

## 2. Frozen bounded GET contracts

### 2.1 Account directory

Existing route: `GET /api/v1/admin/accounts`, root-only through `require_root`.

The route receives a new minimal list response model instead of reusing mutation/session `AdminPublic`:

```text
BaseResponse[list[AccountDirectoryItemView]]
  id: positive integer
  username: non-empty string
  display_name: non-empty string
  enabled: boolean
  is_root: boolean
  access_control_version: integer >= 1
```

Email, phone, IP, active-session count, last login, TOTP/enrollment status, linked LINE identity, role and capabilities
are not part of this page query contract. `role/capabilities` must not drive business navigation. Missing UI slots display
`後端尚未提供 typed ...` rather than fake values.

### 2.2 Masked audit page

Existing route: `GET /api/v1/admin/audits?page=1&page_size=25...`, available to every enabled internal principal
through `require_admin`.

The same package minimally hardens its list view to a closed server-masked shape:

```text
BaseResponse[AdminAuditMaskedPageView]
  items: AdminAuditMaskedItemView[]
  page: integer >= 1
  page_size: integer 1..100
  total: integer >= 0
  total_pages: integer >= 1

AdminAuditMaskedItemView
  audit_id: positive integer
  occurred_at: ISO datetime
  actor_label_masked: string | null
  action_family: authentication | account_security | session | mfa | system | other
  target_label_masked: string | null
  ip_address_masked: string | null
  outcome: success | denied | failed | unknown
  reason_code: bounded safe string | null
```

React does not call `GET /api/v1/admin/audits/{audit_id}` because its current `details` contract permits raw
dict/list/primitive. Audit detail Drawer remains unavailable; no raw `details`, request path, token/session identity,
full IP, payload, PII or internal exception enters DOM/log/fixture/receipt.

### 2.3 Safe job observation

Current `GET /api/v1/jobs/{job_id}` exposes raw `receipt_payload` and `error_payload`, so it is not a React contract.
This package adds the smallest additive observation endpoint without changing queue/worker/caller/domain behaviour:

```text
GET /api/v1/jobs/{job_id}/observation

BaseResponse[JobObservationView]
  job_id: non-empty string
  command_type: assignment_plan_apply
              | finance_import_historical_reprocess_apply
              | finance_import_batch_apply
              | finance_import_correction_apply
              | orders_auto_completion_apply
              | government_subsidy_apply
              | payroll_rebuild_apply
              | staff_payout_apply
  status: queued | running | succeeded | failed | cancelled
  attempt_count: integer >= 0
  max_attempts: integer >= 0
```

The jobs tab follows the existing `require_system_admin` capability boundary and becomes manual job-ID lookup plus
explicit refresh；it is not a fabricated global dashboard. It never
shows LINE queue totals, database pool/latency, anomaly counts, provider acknowledgement, raw receipt/error,
result reference or Domain success. Queue `succeeded` is labelled only as job execution state, not business completion.

This minimal observation GET is independent of the blocked full Durable Job Public Outcome contract because it exposes
no terminal Domain outcome and changes no Core/caller/repository contract. Existing cancel POST remains uncalled and disabled.

## 3. Auth, error and privacy rules

- Account list: sole enabled root only; 401/403 are explicit tab states, not empty list.
- Audit：existing enabled internal principal policy。Job observation：existing `require_system_admin`
  capability policy。React不從role/menu自行推導任一權限。
- All clients read the current volatile memory bearer per request; callers cannot override Authorization.
- Global typed error envelope/correlation applies to 401/403/404/422/500/503; React never branches on raw message text.
- Strict Pydantic and Zod reject missing required, wrong primitive, extra key, null violation and invalid enum.
- Forbidden client schema constructs: `z.any`, `z.unknown`, `z.record`, `.passthrough()`, `.catch()`, `.default()`,
  `.coerce()`, `.preprocess()`, `.transform()`, `as any`, `unknown as`.
- No password, TOTP code, seed, QR/provisioning URI, recovery code, bearer, full IP, email, raw audit/job payload or
  fake job health may appear in production source, DOM, log, fixture, screenshot or receipt.

## 4. UI disposition and stable IDs

### Query-enabled

- `account.page`
- `account.tab.users|totp|audit|jobs`
- `account.users.list|empty|error|retry`
- `account.user.<id>`
- `account.audit.filter|refresh|table|row|pagination|empty|error`
- `account.jobs.lookup|refresh|observation|empty|error`

Tabs load lazily: first visit to each query tab issues at most one request. Returning to a ready tab uses current loaded
data until explicit refresh. Each request has AbortSignal, timeout and generation guard.

### Native disabled / unavailable

- `account.user.create`
- `account.user.enable`, `account.user.disable`
- `account.user.password-reset`, `account.user.session-revoke`
- `account.mfa.enroll`, `account.mfa.reset`, `account.mfa.verify`
- `account.audit.detail`
- `account.jobs.cancel`, `account.jobs.retry`, `account.jobs.run`

All retain their logical visual area, native `disabled`, query-only reason and no handler. TOTP tab may explain the
existing two-step login but may not render simulated QR/secret/code field or claim enrollment status.

## 5. Exact implementation write set (after exact approval only)

### Backend minimal query hardening

- `api/schemas/account_center.py`
- `api/routes/account_center.py`
- `api/schemas/admin_audit.py`
- `api/routes/admin_audit.py`
- `subsystems/access/security_audit_query.py`
- `api/schemas/jobs.py`
- `api/routes/jobs.py`
- `tests/test_access_account_center_public_contract.py` (new)
- `tests/test_access_audit_public_query_contract.py` (new)
- `tests/test_jobs_public_observation_route.py` (new)
- existing focused tests only where exact affected assertions require updates

`BackgroundJobRepository.get_job()` is sufficient for manual observation lookup; no repository/list/schema/worker change
is allowed. Account mutation functions, audit storage, durable Core/callers and source DB rows are read-only inputs.

### React clients/adapters/page

- `ui_react/src/api/access/account_directory_schemas.ts` (new)
- `ui_react/src/api/access/account_directory_errors.ts` (new)
- `ui_react/src/api/access/account_directory_client.ts` (new)
- `ui_react/src/api/access/audit_query_schemas.ts` (new)
- `ui_react/src/api/access/audit_query_errors.ts` (new)
- `ui_react/src/api/access/audit_query_client.ts` (new)
- `ui_react/src/api/jobs/job_observation_schemas.ts` (new)
- `ui_react/src/api/jobs/job_observation_errors.ts` (new)
- `ui_react/src/api/jobs/job_observation_client.ts` (new)
- `ui_react/src/adapters/access/account_query_adapter.ts` (new)
- `ui_react/src/pages/AccountManagementPage.tsx`
- `ui_react/src/pages/AccountManagementPage.css`
- corresponding exact fixtures and focused client/adapter/page/no-fake-mutation/request-budget tests
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-account-query-page-slice/`

`AccountManagementPage.tsx` has exactly one writer. Implementation order is backend view freeze → account client →
audit client → job client → adapter → page/tests → fresh audit. No parallel page writer may apply the older proposed
Account/Audit/Jobs React packages.

Do not modify shared transport/runtime decoder/Auth, LoginPage, App, package/lockfile, other pages, README/main plan,
DB/schema/migration/seed/backfill, worker/caller/provider, Streamlit, entry registry or Phase 5/6 artifacts.

## 6. Request budget and state

| Action | Maximum request |
|---|---:|
| first users-tab load / explicit refresh | one accounts GET |
| first audit-tab load / filter/page/refresh | one audit GET |
| first jobs-tab visit | zero until valid job ID submitted |
| job lookup / explicit refresh | one observation GET |
| tab switch | abort prior generation; no duplicate ready-tab GET |
| local display/filter or disabled control | zero |

Each lane uses `idle | loading | ready | empty | error` and audit additionally `loading_more/page_error` if pagination
is append-based. Stale tab/filter/job responses are discarded. Duplicate audit IDs, page metadata mismatch, account IDs,
or job identity mismatch fail closed. Auth/schema/network/timeout failures never become empty success or local samples.

## 7. Acceptance gates

| Gate | Required proof | Initial status |
|---|---|---|
| G0 Scope | exact approval, latest dirty baseline, one page writer, no mutation/DB | `BLOCKED` pending approval |
| G1 Contract matrix | three GETs, fields, auth, masking, errors, nullability frozen | `NOT_RUN` |
| G2 Backend | account minimal view; masked audit list; safe job observation; 0 write/raw payload | `NOT_RUN` |
| G3 Clients/adapters | strict negative decode, bearer refresh, abort/stale/id mismatch, no inference | `NOT_RUN` |
| G4 Page/safety | real rows, unavailable slots, request budget, all mutations native disabled | `NOT_RUN` |
| G5 Static/regression | focused/full tests, build/lint, UTF-8/diff, secret/PII/write-set scans | `NOT_RUN` |
| G6 Browser | real FastAPI+Vite+user TOTP; root/non-root auth; existing DB GET only | `NOT_RUN` |

Browser must prove root sees accounts, enabled non-root receives the correct account-tab 403, audit follows
`require_admin`, jobs follows `require_system_admin`, and no mutation/non-GET occurs. Happy DOM, API-only 200,
fake session or old screenshot cannot pass G6.

## 8. Existing Work Package succession

After exact approval this page-slice serially carries the query presentation intent of:

- `PROV-20260817-access-account-center-public-contract-hardening` (query fields only);
- `PROV-20260817-access-audit-public-query-hardening`;
- `PROV-20260817-react-admin-phase3c-access-audit-react`;
- `PROV-20260817-react-admin-phase3c-durable-job-observability-react` (safe observation only).

It does not rewrite or silently mark those files completed. Integration Owner performs later index/status succession
after this package evidence closes. Durable Job terminal public outcome and every mutation remain with their original owners.

## 9. DB gate (0 DB change)

| DB gate | Status | Evidence / reason |
|---|---|---|
| Scope | `PASS` | existing-data GET/query boundary only |
| Change inventory | `PASS` | schema/seed/backfill/destructive all zero |
| Static release | `NOT_RUN` | no release change |
| Descriptor | `NOT_RUN` | no owned-object change |
| Read-only plan | `NOT_RUN` | no migration plan; existing DB only browser GET |
| Engine verification | `NOT_RUN` | UI/query evidence is not DB engine evidence |
| Developer acceptance | `NOT_RUN` | no migration or existing DB mutation |

Conclusion: `DB_CHANGE_NOT_READY`. This does not block the approved query-only slice and does not authorize account,
MFA, audit, job or DB mutation.

## 10. Rollback

If a query candidate fails, `#account` may route back to the current Streamlit account/audit display entry where one
exists; unavailable tabs remain explicit otherwise. This is presentation rollback only and never invokes old mutation
handlers or rolls back Access/Job/DB state.

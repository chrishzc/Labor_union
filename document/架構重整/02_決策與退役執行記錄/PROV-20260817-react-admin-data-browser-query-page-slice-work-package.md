---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-react-admin-data-browser-query-page-slice
date: 2026-08-17
owner: Data Browser Query / React Integration Owner
domain: Access / Audit Presentation
subsystem: masked-data-browser-query / React Presentation
initiative: react-admin-migration
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
prerequisites: approved page-slice execution decision; Phase 2C volatile bearer session available
approval_required: 核准此 exact React Data Browser Query Page-Slice Work Package，並採用 Option A
part_identity_decision: Option A recommended; dedicated provisional semantic identity part-data-browser; canonical ordinal late-bound by Integration Owner
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-data-browser-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: relevant page/route/schema/repository/client drift requires fresh read and re-freeze; never overwrite user baseline
blocker: BLOCKED_REAL_BROWSER_EVIDENCE
---

# Phase 3：Data Browser query page-slice 真實資料接線工作包

> Activation：使用者已明確回覆「核准此 exact React Data Browser Query Page-Slice Work Package，並採用 Option A」。

## 0. 單一 activation decision

Data Browser 的 UI Part identity 尚未核准。本包直接納入推薦的 **Option A**，不再建立第三份 gap：

- 建立 dedicated Data Browser UI Part，provisional semantic identity 固定為 `part-data-browser`。
- canonical 數字 Part ID 仍由 Integration Owner 在最新 catalog／未追蹤檔案／inbound links 盤點後 late-bind；
  本包不得自行以最大號碼加一。
- Part 只擁有六個 allowlisted source 的 masked Query、pagination、typed Drawer、browser checklist 與 evidence。
- source correction／generic PATCH、owning-domain repair、entry cutover 與 Streamlit retirement 不屬此 Part。

只有使用者明確回覆 frontmatter 的完整 approval phrase，才同時核准 Option A 與本 page-slice production
write set。未取得該文字時，本包維持 `proposed`；這是唯一 activation blocker，不另立新文件。

## 1. Business scenario 與完成邊界

已完成帳密→TOTP 的內部維運人員進入 React `#data-browser`，從六個固定資料來源選擇一個 source，
以 bounded cursor 查詢 server-masked rows、搜尋 loaded scope、打開同一筆 masked detail Drawer，並能複製
已遮罩的顯示資料。React 不讀 raw DB row、不接受任意 table identifier、不顯示完整電話／身分證／地址／
銀行帳號／raw import payload，也不執行 correction。

本包把現有 `DataBrowserPage.tsx` 的五筆 mock、`Record<string, any>` raw JSON、fake actor/version hash、
clipboard `alert()` 替換為 typed query presentation。完成上限固定為 `query-real-data-validated`；不代表
Data Browser 全 boundary、Phase 5 cutover 或 Streamlit retirement 完成。

## 2. Frozen React source ID ↔ server allowlist

React tab identity 與 public source identity 必須由常數映射；不得把 URL path、table name 或 label 由使用者輸入。

| Existing React tab ID | Canonical public `source_id` | Backend owned source | Primary cursor / row identity | Initial disposition |
|---|---|---|---|---|
| `orders_archive` | `orders` | `orders` | `(case_no)` | wired after masked query contract |
| `clients_archive` | `clients` | `clients` | `(id)` | wired after masked query contract |
| `staff_archive` | `staff` | `staff` | `(id)` | wired after masked query contract |
| `beclass_history` | `beclass_intake` | `beclass_records` | `(id)` | wired after masked query contract |
| `hcm_history` | `hcm_review` | `case_import_hcm_review_rows` | `(id)` | wired after masked query contract |
| `bank_facts_history` | `bank_facts` | `finance_import_rows` | `(id)` | wired after masked query contract |

The backend public route consumes only the six `source_id` values. Internal table names stay repository-owned and
must not be echoed as authorization or SQL input. Unknown/mixed-case/blank/path-traversal source IDs fail closed with
typed `404 source_not_found` or `422 source_id_invalid`; no arbitrary table fallback.

This mapping supersedes the current UI's historical `*_archive` literals as API identities but preserves them as
stable presentation tab IDs. Existing Streamlit legacy `/{table}` callers remain unchanged until per-entry cutover;
the React client uses only the new bounded source route.

## 3. Minimal public query contract

### 3.1 Additive endpoint

```text
GET /api/v1/admin/data-browser/sources/{source_id}
  ?limit=1..100
  [&after=<opaque non-empty cursor>]
  [&query=<trimmed max 100 characters>]
```

- `require_system_admin` means any authenticated enabled internal principal receives the same business query access;
  no client-side role switch, root-only branch or dev token bypass.
- Response and all errors use the current Global typed envelope and correlation contract.
- Stable ordering is server-owned per source; `next_cursor` is opaque, nullable and must advance. React never parses it.
- `query` is a bounded server-side search over allowlisted masked columns only; local search may additionally filter
  loaded rows and must say `loaded scope`.
- Query is 0 commit, 0 UoW mutation, 0 source-correction call, 0 outbox/job/provider.

### 3.2 Strict response view

```text
BaseResponse[DataBrowserMaskedPageView]
  data.source_id: enum(six values)
  data.items: DataBrowserMaskedRowView[]
  data.next_cursor: string | null

DataBrowserMaskedRowView
  source_id: same enum as page
  row_identity: non-empty opaque/display-safe string
  display_title: non-empty server-masked string
  summary_cells: DataBrowserMaskedCellView[]
  detail_cells: DataBrowserMaskedCellView[]
  recorded_at: ISO-8601 string | null
  source_actor_label: masked string | null
  version_identity: 64-hex string | null

DataBrowserMaskedCellView
  field_id: allowlisted non-empty string
  label: non-empty string
  value: string | number | boolean | null
  presentation: text | date | datetime | integer | decimal | status | masked
```

Rows and cells are arrays of strict typed objects; public schema and Zod must not use `dict[str, Any]`, `z.record`,
catch-all, raw JSON or arbitrary column descriptors. Duplicate `row_identity`／`field_id`, source mismatch, unknown
presentation, malformed cursor, extra key or mask policy drift fails closed.

### 3.3 Mask/redaction allowlist

| `source_id` | Allowed server-owned display fields | Always omitted/redacted |
|---|---|---|
| `orders` | case identity, canonical status, service date range, created/updated time | client phone/address, raw contract/import payload, unrestricted amounts |
| `clients` | masked name, city, masked identity-status label, created/updated time | full phone, address, identity number, notes/raw form |
| `staff` | masked name, city, enabled/lifecycle label if authoritative, created/updated time | phone, email, birthday, bank, certificate files, special notes |
| `beclass_intake` | masked query/record identity, intake status, received time, masked subject | survey_details/raw workbook/form payload, phone/email/address |
| `hcm_review` | masked review identity, status, issue-code labels, received/reviewed time | original/canonical raw payload JSON, source row personal data |
| `bank_facts` | opaque fact identity, transaction date, flow/status label, masked amount string | bank account, counterparty account/name, raw description/reference, raw row |

Masking occurs before Pydantic serialization. A client-side `***` replacement is not privacy evidence. Unknown source
column or missing masking rule rejects the row/page; it must not silently omit only the failing field and claim success.

The list row already includes the full approved masked `detail_cells`, so opening Drawer issues **0 additional GET**.
This is the recommended page-slice minimum and avoids a second detail contract/request budget.

## 4. UI slot disposition and stable IDs

### Wired query/presentation

- `data-browser.page`
- `data-browser.source.orders|clients|staff|beclass_intake|hcm_review|bank_facts`
- `data-browser.query`, `data-browser.query.submit`, `data-browser.query.retry`
- `data-browser.loaded-count`, `data-browser.next-page`
- `data-browser.row.<source_id>.<row_identity>`
- `data-browser.drawer.open`, `data-browser.drawer`, `data-browser.drawer.close`
- `data-browser.drawer.copy-masked`

`copy-masked` may copy only the typed `detail_cells` presentation view. It uses accessible inline status
`data-browser.drawer.copy-status`; no `alert()`、raw JSON、token or hidden cell.

### Native disabled/deferred

- `data-browser.patch`
- `data-browser.source-correction.preview`
- `data-browser.source-correction.apply`
- any edit/save/delete/upload/export-raw control

All remain in their intended visual/action area with native `disabled`, explicit query-only reason, no handler,
0 non-GET and 0 fake success. The legacy backend PATCH remains 410; source-correction Preview/Apply routes are not
called, tested as page success or modified by this package.

## 5. Exact implementation write set (after exact approval only)

### Backend minimal query boundary

- `api/schemas/data_browser.py`
- `api/routes/data_browser_admin.py`
- `subsystems/access/data_browser_maintenance.py`
- `infrastructure/mysql/data_browser_query_repository.py` (new)
- `tests/test_data_browser_admin_route.py`
- `tests/test_data_browser_query_contract.py` (new)
- `tests/test_data_browser_privacy.py` (new)

Backend changes are limited to the additive six-source masked GET, typed errors and its read-only repository. Existing
legacy table GET, retired PATCH and source-correction routes remain unchanged for current Streamlit compatibility.

### React bounded slice

- `ui_react/src/api/data_browser/data_browser_query_schemas.ts` (new)
- `ui_react/src/api/data_browser/data_browser_query_errors.ts` (new)
- `ui_react/src/api/data_browser/data_browser_query_client.ts` (new)
- `ui_react/src/adapters/data_browser/data_browser_query_adapter.ts` (new)
- `ui_react/src/pages/DataBrowserPage.tsx`
- `ui_react/src/pages/DataBrowserPage.css`
- `ui_react/src/tests/fixtures/data_browser/data_browser_query_contract_fixtures.ts` (new)
- `ui_react/src/tests/data_browser_query_client.test.ts` (new)
- `ui_react/src/tests/data_browser_query_adapter.test.ts` (new)
- `ui_react/src/tests/data_browser_page_real_data.test.tsx` (new)
- `ui_react/src/tests/data_browser_no_fake_mutation.test.tsx` (new)
- `ui_react/src/tests/data_browser_request_budget.test.tsx` (new)

### Validation/evidence owned by Integration Owner

- late-bound Option A `part-data-browser` metadata/checklist artifacts; initial result `NOT_RUN`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-data-browser-query-page-slice/`

Do not modify shared transport/runtime decoder/Auth, `App.tsx`, package/lockfile, README/main plan, other page,
DB/schema/migration/seed/backfill, Streamlit source, entry registry or Phase 5/6 files in this package.

## 6. Request budget, state and failure behaviour

| User action | Request maximum |
|---|---:|
| initial page/source | one GET for the selected source |
| source tab switch | one GET for the new source; abort previous generation |
| explicit search submit | one GET; empty query restores first page |
| local loaded-scope filtering | 0 |
| next cursor click | one GET for the exact unseen cursor |
| Drawer open/close/copy | 0 |
| disabled PATCH/correction controls | 0 |

Client reads the current memory bearer per request, cannot be given caller Authorization, supplies AbortSignal,
timeout and correlation, and supports no non-GET method. Page state is a discriminated union:

```text
idle → loading → ready | empty | error
ready → loading_more → ready | page_error
source/query switch → abort previous → loading
```

Generation guard discards stale source/query/cursor responses. Duplicate row/cursor or non-forward cursor fails
closed. `401/403/404/422/500/503`, schema/masking mismatch, timeout, network and abort never become an empty success
or mock fallback.

## 7. Acceptance gates

| Gate | Required proof | Initial status |
|---|---|---|
| G0 Activation/scope | exact approval includes Option A; latest namespace/dirty baseline; exact write set | `PASS` |
| G1 Source/privacy matrix | six source mappings, fields, masking, cursor, auth/error contract frozen | `PASS` |
| G2 Backend query | success/empty/pagination/search/unknown source/auth/typed error/0-write/privacy tests | `PASS` |
| G3 Client/adapter | strict negative decode, token refresh, abort/stale/cursor/duplicate tests, no raw row | `PASS` |
| G4 Page/control | six tabs, loaded scope, Drawer/copy, request budget, disabled correction, no mock | `PASS` |
| G5 Static/regression | focused/full tests, build/lint, UTF-8, diff, secret/PII/write-set scans | `PASS` |
| G6 Browser GET UI | real FastAPI+Vite+user TOTP, six-source Network↔DOM, existing DB GET only | `NOT_RUN` |

Only applicable G0–G6 evidence may yield `query-real-data-validated`. Browser evidence cannot be replaced by
Happy DOM, API 200, raw DB query or old Streamlit screenshot.

## 8. DB gate (0 DB change)

| DB gate | Status | Evidence / reason |
|---|---|---|
| Scope | `PASS` | bounded read-only query; no DB artifact write |
| Change inventory | `PASS` | schema/seed/backfill/destructive all zero |
| Static release | `NOT_RUN` | no release change |
| Descriptor | `NOT_RUN` | no owned-object change |
| Read-only plan | `NOT_RUN` | no migration plan; existing DB only browser GET |
| Engine verification | `NOT_RUN` | no test DB required for page slice; UI evidence is not engine evidence |
| Developer acceptance | `NOT_RUN` | no migration or existing DB mutation |

Conclusion: `DB_CHANGE_NOT_READY`. This does not block the query-only page slice after exact approval and does not
authorize source correction or any DB mutation.

## 9. Consolidation and rollback

After exact approval this single page-slice is the query successor for the still-proposed
`PROV-20260817-react-admin-phase3d-db-query-public-contract-hardening`,
`PROV-20260817-react-admin-phase3d-db-r-react` and Option A identity decision. Their historical bytes are not
rewritten here; Integration Owner later synchronizes status/index once evidence closes.

On query failure, `#data-browser` can route back to the current Streamlit Data Browser display entry. This is UI
rollback only; no Domain/DB state rollback occurs. Entry cutover and retirement remain separate Phase 5/6 actions.

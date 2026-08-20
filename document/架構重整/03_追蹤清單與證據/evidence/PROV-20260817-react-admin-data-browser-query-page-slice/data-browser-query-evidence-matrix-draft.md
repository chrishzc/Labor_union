# Data Browser Query Page-Slice Evidence Matrix（Draft）

Status: `DRAFT` / awaiting exact approval and Option A decision. This file is not a freeze receipt or PASS evidence.

Work Package: `PROV-20260817-react-admin-data-browser-query-page-slice`

## 1. Option A identity

| Item | Draft value | Gate |
|---|---|---|
| semantic Part identity | `part-data-browser` | exact approval required |
| canonical ordinal | not assigned | Integration Owner late-binds after catalog/collision scan |
| entry | `#data-browser` | Phase 5 switch remains separate |
| rollback display | existing Streamlit Data Browser | query display only; not mutation rollback |
| owner | masked source Query/detail/copy evidence | correction and cutover excluded |

## 2. React tab ↔ canonical source matrix

| React tab ID | Public `source_id` | Repository source | Row identity | Required browser observation |
|---|---|---|---|---|
| `orders_archive` | `orders` | `orders` | case number | masked order row and Drawer |
| `clients_archive` | `clients` | `clients` | positive id | masked client row; no phone/address |
| `staff_archive` | `staff` | `staff` | positive id | masked staff row; no contact/bank |
| `beclass_history` | `beclass_intake` | `beclass_records` | positive id | intake row; no survey/raw form |
| `hcm_history` | `hcm_review` | `case_import_hcm_review_rows` | positive id | review row; no raw payload |
| `bank_facts_history` | `bank_facts` | `finance_import_rows` | positive id | masked bank fact; no account/counterparty |

Unknown, blank, mixed-case and traversal source IDs must fail closed before repository query.

## 3. Typed response field matrix

| JSON path | Type | Required/nullable | Privacy / UI disposition |
|---|---|---|---|
| `data.source_id` | six-value enum | required/non-null | internal source label mapping |
| `data.items` | strict row array | required/non-null | table rows |
| `data.next_cursor` | opaque string/null | required/nullable | manual next-page only |
| `items[].source_id` | same enum | required/non-null | must match page source |
| `items[].row_identity` | non-empty string | required/non-null | stable DOM identity; server-safe |
| `items[].display_title` | non-empty string | required/non-null | server masked |
| `items[].summary_cells` | strict cell array | required/non-null | table display |
| `items[].detail_cells` | strict cell array | required/non-null | Drawer/copy display; no extra GET |
| `items[].recorded_at` | ISO string/null | required/nullable | display only |
| `items[].source_actor_label` | string/null | required/nullable | masked label only |
| `items[].version_identity` | 64-hex/null | required/nullable | lineage display, not authorization |
| `cells[].field_id` | allowlisted string | required/non-null | source-specific allowlist |
| `cells[].label` | non-empty string | required/non-null | server-owned label |
| `cells[].value` | scalar/null | required/nullable | no dict/list/raw JSON |
| `cells[].presentation` | closed enum | required/non-null | safe renderer selection |

## 4. UI and request matrix

| Surface/control | Disposition | Request budget / assertion |
|---|---|---|
| `data-browser.page` | wired | selected source state visible |
| six `data-browser.source.*` tabs | wired | one GET per switch; prior abort |
| `data-browser.query.submit` | wired | one GET; query max 100 |
| `data-browser.next-page` | wired when cursor exists | one unseen cursor GET |
| `data-browser.drawer.open` | wired from loaded row | 0 GET |
| `data-browser.drawer.copy-masked` | wired | 0 GET; typed detail cells only; inline status |
| `data-browser.patch` | native disabled | 0 request |
| `data-browser.source-correction.preview` | native disabled | 0 request |
| `data-browser.source-correction.apply` | native disabled | 0 request |

## 5. Mandatory negative vectors

- source allowlist: blank, unknown, mixed-case, `%2e%2e`, slash, SQL-looking value;
- envelope/row/cell: missing required, wrong primitive, extra key, null violation, unknown presentation;
- privacy: phone, identity number, full address, bank account, counterparty, raw survey/HCM/import payload never appears;
- pagination: duplicate row, repeated/non-forward cursor, source mismatch, stale source/query response;
- auth/errors: missing/rotated token, 401/403/404/422/500/503, timeout/network/abort;
- UI: no `mockData`, raw JSON, `Record<string, any>`, `alert/confirm/prompt`, non-GET or correction handler;
- browser: each source Network response must match its DOM table/Drawer; existing DB remains GET-only.

## 6. Evidence placeholders

| Artifact | Initial status |
|---|---|
| Option A namespace/collision receipt | NOT_RUN |
| `contract-field-matrix.md` | NOT_RUN |
| `candidate-change-inventory.md` | NOT_RUN |
| `verification-receipt.md` | NOT_RUN |
| `browser-smoke-receipt.md` | NOT_RUN |
| `open-findings.md` | NOT_RUN |

No DB engine/migration receipt is created by this query-only matrix.

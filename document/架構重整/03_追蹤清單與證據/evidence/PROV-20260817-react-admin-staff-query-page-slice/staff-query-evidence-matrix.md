---
doc_type: evidence-matrix
declared_status: in-progress
identity: PROV-20260817-react-admin-staff-query-page-slice-evidence-matrix
date: 2026-08-17
owner: Staff Query / React Integration Owner
work_package: PROV-20260817-react-admin-staff-query-page-slice
source_of_truth: api/routes/staff.py; api/schemas/staff_summary.py; ui_react/src/pages/StaffPage.tsx
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# Staff query page-slice evidence matrix（草案）

> Contract／component implementation 已通過本地 focused evidence；真 browser 尚未執行。本文件不是
> mutation、entry cutover 或 Streamlit retirement 證據。

## 1. API contract matrix

| Boundary | Backend source | Frontend schema／view | UI disposition | Required evidence |
|---|---|---|---|---|
| `GET /api/v1/staff/summaries` query | `api/routes/staff.py::get_staff_summaries` | `StaffDirectoryQueryParams` | `wired` | request URL has only bounded params; no `/api/v1/staff` |
| `page_size` | FastAPI `Query(1..200)` | integer validation, explicit `200` initial | `wired` | invalid bounds fail typed／validation path |
| `after_id` | positive cursor query | positive integer optional | `wired` | forward-only cursor; repeated cursor rejected |
| `staff_id` | exact positive lookup | positive integer optional | `out-of-scope in first page` | no deep-link fetch unless separately enabled |
| `after_id + staff_id` | route validation | client refuses combination | `typed error` | stable validation code, no raw `detail` branch |
| `success` | `BaseResponse` | required boolean | `wired` | missing／wrong primitive negative test |
| `message` | `BaseResponse` | required string | `not rendered as business state` | strict decode only |
| `data.items` | `StaffSummaryPageView.items` | strict array of `StaffDirectorySummary` | `wired` | empty and duplicate item tests |
| `data.items[].id` | `StaffSummaryView.id`, `gt=0` | strict positive integer | `wired` | server id appears unchanged in DOM identity |
| `data.items[].name` | nullable string | `.nullable()` | `wired` | null renders unavailable／—, never fake name |
| `data.items[].phone` | nullable string | `.nullable()` | `wired` | null renders unavailable／—, no masking guess |
| `data.next_cursor` | nullable positive integer | required nullable integer | `wired when present` | second page only by manual stable control |
| `error` | optional nullable string | optional nullable string | `transport/error only` | never drives retry/action by Chinese message |
| unauthorized／forbidden | `require_system_admin` route guard | typed client error | `auth error` | no token means zero fetch; 401/403 fail closed |
| internal query failure | `internal_query_error` | typed transport error | `error state` | no empty fallback; correlation retained |

## 2. UI slot matrix

| UI slot／stable ID | Existing visual source | Server data | Disposition | Anti-fake assertion |
|---|---|---|---|---|
| `staff.page` | StaffPage shell | none | `wired` | route renders without mock data |
| `staff.tab.roster` | existing roster tab | none | `wired` | tab switch emits 0 GET |
| `staff.tab.preferences` | existing tab | no directory field | `unavailable/disabled` | no profile literal or mutation |
| `staff.tab.unavailability` | existing tab | no block field | `unavailable/disabled` | no dates/reasons/status literals |
| `staff.directory.query` | roster load | summaries page | `wired` | initial GET ≤1 |
| `staff.card.<id>` | roster card | `id/name/phone` | `wired` | stable server numeric id; no `STF-*` |
| `staff.card.status` | status pill | none | `unavailable` | no active/leave inference |
| `staff.card.location` | service area | none | `unavailable` | no location literal |
| `staff.card.experience` | experience／score | none | `unavailable` | no years/score calculation |
| `staff.card.notes` | notes block | none | `unavailable` | no `specialNotes` mock |
| `staff.card.skills` | skill chips | none | `unavailable` | no skill chips from mock |
| `staff.card.certifications` | conduct/medical labels | none | `unavailable` | no validity inference or count |
| `staff.drawer.open.<id>` | existing Drawer open | loaded summary only | `wired` | open adds 0 GET |
| `staff.drawer.resume` | resume/profile block | none | `unavailable` | no master facts |
| `staff.drawer.attachments` | certificate block | none | `unavailable` | no upload or approval |
| `staff.drawer.bank` | masked bank block | none | `unavailable` | no account/PII display |
| `staff.master.create` | header button | no command contract | `native-disabled` | no alert/confirm/fetch |
| `staff.master.retire` | card action | lifecycle mutation out-of-scope | `native-disabled` | no local retirement |
| `staff.preferences.preview/apply` | preference controls | mutation out-of-scope | `native-disabled` | no local profile update |
| `staff.availability.*` | leave/pause controls | mutation out-of-scope | `native-disabled` | no Date.now/day count/overlap |
| `staff.lifecycle.*` | lifecycle controls | mutation out-of-scope | `native-disabled` | no fake receipt/status |
| `staff.directory.next-page` | new minimal pagination affordance | `next_cursor` | `wired when present` | one manual GET; no prefetch |

## 3. Request and browser evidence matrix

| Scenario | Expected Network | Expected DOM | Evidence required |
|---|---|---|---|
| authenticated initial roster | exactly one GET summaries | server `id/name/phone` card values | browser Network + DOM receipt |
| empty page | one GET 200 with empty items | explicit empty state, not error | focused page test; browser only if existing DB returns empty |
| cursor page | one GET per manual next cursor | append unique cards | request-budget test + browser if cursor exists |
| drawer open／close | zero network | summary-only Drawer; unavailable detail slots | browser Network + DOM |
| tab switch | zero network | preferences/unavailability unavailable | page test + browser |
| 401／403 | no token fetch or auth error response | auth-required/error state | route/client negative test; browser after logout/session expiry |
| malformed payload | one response, strict decode failure | typed error; no cards | client negative test |
| timeout／abort | request cancelled/typed timeout | no stale cards or fake empty | client/page test |
| non-GET scan | zero POST/PUT/PATCH/DELETE | disabled controls remain inert | static scan + browser Network |
| existing DB safety | GET only | no data mutation claim | command/network evidence; no DB engine receipt required |

## 4. Required completion receipts

| Receipt | Path／owner | Status |
|---|---|---|
| contract-field-matrix | this matrix, Integration Owner | `local-implemented` |
| candidate-change-inventory | `candidate-change-inventory.md` | `complete` |
| verification-receipt | `verification-receipt.md` | `focused-pass` |
| browser-smoke-receipt | `browser-smoke-receipt.md` | `awaiting-real-browser` |
| open-findings | `open-findings.md` | `current` |

Completion may be `query-real-data-validated` only after the required client/page/route tests, static gates and
real TOTP browser Network↔DOM evidence are present. This matrix must not be edited to claim PASS when any required
receipt is absent; mutation, DB engine, entry cutover and Streamlit retirement evidence are outside this slice.

## 5. Current gate result

| Gate | Status | Evidence |
|---|---|---|
| G0 scope／write set | `PASS` | exact approval、candidate inventory |
| G1 contract matrix | `PASS` | this file、strict Zod/Pydantic field tests |
| G2 route auth／typed conflict | `PASS` | 12 focused/bounded pytest |
| G3 client／adapter | `PASS` | 9 focused Vitest、exact TypeScript |
| G4 page／control | `PASS` | 7 focused Vitest、anti-fake scan |
| G5 static | `PASS`（scoped） | oxlint、UTF-8、headers、diff、secret scan |
| G6 real browser GET UI | `NOT_RUN` | `browser-smoke-receipt.md` |

Current ceiling remains `in-progress-local-validated`; not `query-real-data-validated`.


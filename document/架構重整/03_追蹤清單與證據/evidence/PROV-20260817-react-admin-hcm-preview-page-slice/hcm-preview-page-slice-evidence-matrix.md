# HCM Preview page-slice evidence matrix draft

> Status: `DRAFT_INPUT_ONLY`。本文件是 `PROV-20260817-react-admin-hcm-preview-page-slice`
> 的驗收輸入，不是 contract freeze、runtime receipt、approval 或完成證據。所有 `PASS` 欄位必須
> 由 exact approval 後的 fresh command／真 TOTP browser evidence 填入；不得複製前一 identity 的數字。

## 1. Scope identity

| Item | Value |
|---|---|
| Work Package | `PROV-20260817-react-admin-hcm-preview-page-slice` |
| Page | `#data-import` / `DataImportPage` |
| Bounded slice | HCM Current workbook file-select → zero-write Preview → aggregate DOM |
| Allowlisted action | `POST /api/v1/case-import/hcm/workbooks/preview` only |
| Approval | `核准此 exact React HCM Preview Page-Slice Work Package` |
| Browser auth | real account/password → six-digit TOTP; memory bearer only |
| DB policy | existing DB observation only; no new DB, seed, migration, repair or mutation |
| Completion ceiling | `query-real-data-validated-preview-only` |
| Evidence root | this directory |

## 2. Frozen source-to-UI matrix (draft)

| Source / symbol | Transport / type | Required constraint | UI slot / stable ID | Draft disposition | Evidence to collect |
|---|---|---|---|---|---|
| `DataImportPage` category shell | React presentation | six cards remain present | `imports.page` | wired | DOM card count／labels |
| HCM open action | local button | no request on open | `imports.hcm-current.open-preview` | wired | Network delta = 0 |
| `HcmWorkbookSnapshot.fromFile` | local immutable bytes | `.xlsx`, non-empty, ≤20 MiB, SHA-256 | `imports.hcm-current.file` | wired | selected file + no POST |
| `preview_hcm_workbook` | `POST /api/v1/case-import/hcm/workbooks/preview` | multipart field exactly `workbook`; one explicit request | `imports.hcm-current.preview` | allowlisted | Network method/path/count |
| `HcmWorkbookPreviewView.source_content_digest` | lowercase 64-hex | equals snapshot SHA-256 | `imports.hcm-current.preview-summary` | wired | response↔DOM digest |
| `source_row_count` | strict integer ≥0 | no client derivation | summary metric | wired | response↔DOM value |
| `ready_count` | strict integer ≥0 | server aggregate only | summary metric | wired | response↔DOM value |
| `ready_with_warning_count` | strict integer ≥0 | server aggregate only | summary metric | wired | response↔DOM value |
| `review_required_count` | strict integer ≥0 | server aggregate only | summary metric | wired | response↔DOM value |
| `preview_fingerprint` | lowercase 64-hex | lineage display only; does not unlock Apply | summary lineage | wired | response↔DOM fingerprint |
| adapter conservation check | `ready + warning + review == source rows` | fail closed on mismatch | preview summary | wired | negative test / error DOM |
| row-level contract | no public typed row view | no inference from counts | `imports.hcm-current.row-detail-unavailable` | unavailable | exact unavailable text |
| HCM Apply | `POST /workbooks/apply` exists but out of scope | no Apply／receipt／UoW in this slice | `imports.hcm-current.open-apply`, `imports.hcm-current.apply` | native disabled | click has 0 request |
| HCM historical | route retired (`410`) | never call from this page | `imports.hcm-historical.preview/apply` | retired/disabled | disabled controls |
| Client BeClass | separate bounded family | no shared HCM client | `imports.client-beclass.preview/apply` | unavailable/disabled | disabled controls |
| Staff historical | separate bounded family | no shared HCM client | `imports.staff-historical.preview/apply` | unavailable/disabled | disabled controls |
| Historical orders | separate bounded family | no local status inference | `imports.historic-orders.preview/apply` | unavailable/disabled | disabled controls |
| Bank statements | Finance Import owner | no finance result inference | `imports.bank-statements.preview/apply` | unavailable/disabled | disabled controls |

## 3. Decoder / negative matrix

| Case | Input mutation | Required result | Actual evidence |
|---|---|---|---|
| missing required data field | remove one of six fields | `ApiDecodeError`／known contract error; no preview DOM | TODO after approval |
| wrong primitive | string for count or boolean for digest | reject; no aggregate render | TODO after approval |
| extra field | add envelope／data unknown key | strict decoder rejects | TODO after approval |
| null violation | null in required digest/count | reject; no stale preview | TODO after approval |
| invalid digest | non-lowercase／non-64-hex | reject | TODO after approval |
| negative/fraction count | `-1` or `1.5` | reject | TODO after approval |
| row conservation drift | counts do not sum to source rows | adapter throws bounded contract error | TODO after approval |
| source digest mismatch | response digest ≠ snapshot SHA-256 | reject and clear/avoid usable preview | TODO after approval |
| no memory session | token absent | zero fetch; auth error presentation | TODO after approval |
| timeout/network/abort | transport failure | known error; no success/empty masquerade | TODO after approval |

## 4. Browser Network↔DOM checklist

| Step | Observation | Required assertion | Evidence field |
|---:|---|---|---|
| 1 | login | real password then six-digit TOTP; no dev token | timestamp／sanitized screenshot ref |
| 2 | page load | six cards present; no HCM POST before click | Network count |
| 3 | open Drawer | `imports.hcm-current.open-preview` opens; 0 request | Network delta |
| 4 | choose `.xlsx` | snapshot/hash only; Preview enabled; 0 request | file name sanitized／Network delta |
| 5 | click Preview | exactly one allowlisted POST; multipart key `workbook`; status recorded | method/path/status/count |
| 6 | response mapping | six server fields equal visible aggregate/lineage DOM | sanitized response↔DOM table |
| 7 | row slot | exact unavailable message; no fake row/case/warning story | DOM text |
| 8 | Apply controls | all Apply disabled; click causes 0 request／alert／confirm | control audit |
| 9 | same name, different bytes | old summary clears; no auto POST; new explicit click gets new lineage | digest pair／Network count |
| 10 | close/abort | pending request aborted or stale response discarded | Network／DOM state |
| 11 | reload/session boundary | no bearer means no HCM fetch; auth failure not empty success | sanitized Network |

## 5. Request budget

| Operation | Max requests | Allowed method/path |
|---|---:|---|
| open Drawer | 0 | none |
| choose file | 0 | none |
| explicit Preview click | 1 | `POST /api/v1/case-import/hcm/workbooks/preview` |
| duplicate click while loading | 0 additional | none |
| close／replace file | 0 additional | abort/discard only |
| five other cards | 0 | none |
| any Apply control | 0 | none |

Any non-allowlisted POST/PUT/PATCH/DELETE is a hard failure and must be recorded as `BLOCKED_SCOPE`.

## 6. Gate receipt template

| Gate | Status (`PASS`/`BLOCKED`/`NOT_RUN`) | Evidence path／command | Notes |
|---|---|---|---|
| G0 scope／fresh baseline | `NOT_RUN` | exact approval + fresh `git status` | fill after approval |
| G1 contract matrix | `NOT_RUN` | this matrix + source line audit | draft is not PASS |
| G2 client／adapter | `NOT_RUN` | focused Vitest | do not copy old counts |
| G3 page／UI slots | `NOT_RUN` | page test + DOM inspection | five cards disabled |
| G4 anti-fake/network | `NOT_RUN` | browser Network + control audit | Preview POST only |
| G5 static | `NOT_RUN` | build/lint/UTF-8/diff/secret scan | scoped output |
| G6 real browser | `NOT_RUN` | `browser-smoke-receipt.md` | real TOTP required |

## 7. Explicit exclusions

This draft does not authorize or prove HCM Apply／receipt／archive／outer-UoW、warning transition、row
correction、historical import、other five import families、DB engine migration、entry cutover 或 Streamlit
retirement。POST Preview 的 HTTP method 不會改變這些 exclusions。


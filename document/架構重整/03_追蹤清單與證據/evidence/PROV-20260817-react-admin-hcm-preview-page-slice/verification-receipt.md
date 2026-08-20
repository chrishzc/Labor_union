# HCM Preview page-slice verification receipt

Candidate verified after the final test edits on `2026-08-17T11:15:11+08:00`.

## Command results

| Check | Command | Status | Current result |
|---|---|---|---|
| Focused React | `npm test -- src/tests/hcm_workbook_client.test.ts src/tests/hcm_workbook_adapter.test.ts src/tests/data_import_hcm_preview_flow.test.tsx src/tests/data_import_no_fake_mutation.test.tsx` | PASS | 4 files／17 tests, 0 failed |
| Focused backend | `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase4a-hcm-page-slice -q tests/test_hcm_import_router.py tests/test_hcm_workbook_import.py` | PASS | 10 passed; includes Preview zero-write repository assertions |
| Production build | `npm run build` | PASS | TypeScript + Vite, 98 modules; existing 610.15 kB chunk advisory disclosed |
| Lint | `npm run lint` | PASS | exit 0; two existing `MasterLayout.tsx` Fast Refresh warnings outside this write set |
| Strict UTF-8 | strict decoder + no-BOM check over 13 scoped source/test/doc paths | PASS | 13/13 |
| Whitespace | scoped trailing-whitespace scan + `git diff --check` for edited tests | PASS | no errors |
| Header audit | first documentation block of both edited tests | PASS | exactly one Traditional Chinese File/Description header per file |
| Skip scan | `.skip/.todo/.only` over four focused test files | PASS | 0 matches |
| Secret scan | scoped high-confidence credential/private-key patterns | PASS | 0 matches |
| Forbidden production scan | storage／fake dialogs／mockData／Apply／ingest／historical／resubmission paths in HCM React production closure | PASS | 0 matches |

## Claim ledger

| Claim | Source | Status | Scope and limit |
|---|---|---|---|
| File boundary is `.xlsx`, non-empty, ≤20 MiB and immutable snapshot | `hcm_workbook_client.test.ts`; `HcmWorkbookSnapshot` fresh read | passed | component/client boundary; browser file picker still pending |
| Preview uses only `POST /api/v1/case-import/hcm/workbooks/preview` with multipart `workbook` and fresh memory bearer | client test + production client inspection | passed | real Network capture pending |
| Missing session and pre-aborted signal cause zero fetch | client focused tests | passed | real browser session-expiry capture pending |
| Server/local digest mismatch and strict schema drift fail closed | client focused negative tests | passed | no raw server payload used |
| Adapter maps only aggregate and rejects non-conserved counts | adapter focused tests | passed | does not prove row-level public contract exists |
| Open Drawer and file selection send zero Preview requests; one explicit click sends at most one | page flow focused test | passed | component request budget; browser Network pending |
| Close aborts pending Preview and stale response cannot overwrite reopened generation | page flow focused test | passed | deterministic component evidence |
| HCM Apply and other five card controls are native disabled and create zero follow-up request | page/no-fake focused tests | passed | browser click audit pending |
| Backend service Preview is zero-write | `test_preview_is_zero_write_and_apply_requires_matching_fingerprint` before the test's separately invoked Apply | passed | proves Preview itself leaves claims/receipts empty; does not approve Apply |
| Real account/password→TOTP Network↔DOM | no accessible authenticated browser session in this execution | not_run | tracked in `browser-smoke-receipt.md` |

## Page-slice gates

| Gate | Status | Evidence |
|---|---|---|
| G0 scope／fresh baseline | PASS | exact approval relayed by Integration Owner; fresh hashes and zero-production-change inventory |
| G1 contract | PASS | current route/schema/client/adapter fresh-read and evidence matrix; one allowlisted Preview path |
| G2 client／adapter | PASS | focused client/adapter tests |
| G3 page／UI | PASS | focused file→Preview→aggregate DOM and disabled-control tests |
| G4 anti-fake／request budget | PASS | single-request, abort/stale, Apply zero-follow-up tests + forbidden scan |
| G5 static | PASS | build, lint exit 0, UTF-8, diff, header, skip and secret scans |
| G6 real browser | NOT_RUN | awaiting real TOTP browser Network↔DOM evidence |

Overall package remains `in-progress` / `AWAITING_REAL_BROWSER_EVIDENCE`. No production defect was found in the authorized HCM Preview slice, so no production file was changed.

## DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | PASS | approved Preview-only package; 0 DB write set |
| Change inventory | PASS | no schema／seed／backfill／destructive change |
| Static release gate | NOT_RUN | no release artifact |
| Descriptor gate | NOT_RUN | no owned-object change |
| Read-only plan gate | NOT_RUN | no DB plan required or executed |
| Engine verification gate | NOT_RUN | POST Preview is not DB engine evidence |
| Developer acceptance gate | NOT_RUN | `union_db` not mutated or migrated |

Conclusion: `DB_CHANGE_NOT_READY`; this does not invalidate the current component/focused Preview evidence and does not authorize Apply.


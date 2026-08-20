# Anomalies Query Page-Slice Verification Receipt

Status: `blocked-browser-evidence`; local candidate only.
Work Package: `PROV-20260817-react-admin-anomalies-query-page-slice`
Baseline: `main@8615225481c8f72a9629289285516189b270cb36`

| Check | Command | Result |
|---|---|---|
| Focused Vitest | `npm test -- --run src/tests/anomaly_query_client.test.ts src/tests/anomaly_query_adapter.test.ts src/tests/anomalies_page_real_data.test.tsx src/tests/anomalies_no_fake_mutation.test.tsx src/tests/anomalies_detail_referral_flow.test.tsx src/tests/challenger_phase2d_anomalies.test.tsx` | PASS: 6 files / 78 tests |
| Scoped lint | `npx oxlint <Anomalies client/schema/adapter/page/tests>` | PASS: exit 0 |
| Full Vitest | `npm test -- --reporter=dot` | NOT PASS: 44 files / 524 tests; 441 passed, 83 failed, failures are existing Orders drift outside this slice |
| Build | `npm run build` | NOT PASS: existing Orders schema/client/detail-adapter/challenger compile drift; no Anomalies diagnostic in output |
| Whitespace check | scoped `rg` trailing-whitespace scan over candidate files | PASS: no reported trailing whitespace |
| UTF-8 | strict UTF-8 read of candidate text files | PASS |
| Secret scan | scoped search for production secret patterns | PASS: no production secret; tests retain named non-secret placeholder bearer labels |
| Browser Network↔DOM | real FastAPI + Vite + user TOTP | NOT_RUN: awaiting browser acceptance |

Focused tests cover lazy detail/referral calls, strict response decoding, typed adapter mapping, stale close,
independent list errors, existing UI slots and disabled mutation controls. The full suite/build limitation is not
silently converted to PASS and belongs to pre-existing Orders worktree drift.

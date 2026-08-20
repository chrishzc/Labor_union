# Phase 3A Open Findings

## F-01 — Full React regression repaired

- Status: `RESOLVED`
- Evidence: `verification-receipt.md`
- Exact result: initial 12 failures were repaired by their owning Phase 2B／2D integration scope. The fresh final
  integration run is 43 files／510 tests passed. An unintended test-only request to `localhost:3000` was also
  removed by mocking the approved service-date query in `orders_page_real_data.test.tsx`.

## F-02 — Real browser Session and controlled data unavailable

- Status: `OPEN_BLOCKER`
- Evidence: `browser-smoke-receipt.md`
- Fresh observation: in-app browser目前停在帳密頁；先前由operator登入的Chrome沒有可用控制連線，故未讀取或
  搬移任何Session資料。
- Required closure: fresh two-step login plus disposable ticket/binding data and Network → typed DOM → re-query evidence.

## F-03 — Bundle size warning

- Status: `OPEN_NON_BLOCKING_FOR_FOCUSED_SCOPE`
- Evidence: `npm run build` generated a chunk above 500 kB.
- Disposition: performance follow-up; no router/build hotspot expansion was authorised in Phase 3A.

## F-04 — Existing Fast Refresh warnings

- Status: `OPEN_NON_BLOCKING_FOR_FOCUSED_SCOPE`
- Evidence: two `MasterLayout.tsx` warnings from `npm run lint`.
- Disposition: shared shell hotspot is outside Phase 3A exact write set.

## F-05 — React test `act(...)` warnings

- Status: `OPEN_NON_BLOCKING_TEST_DEBT`
- Evidence: final `npm test` output on 2026-08-17.
- Scope: pre-existing route-guard and adversarial race tests emit state-update warnings; the ErrorBoundary test also
  deliberately emits its captured crash to stderr.
- Disposition: tests pass and no unexpected network access remains, but the suite is not described as warning-free.
  Repair belongs to a dedicated test-harness/shared-shell scope rather than Phase 3A production code.

## F-06 — Identity Apply completion inference

- Status: `RESOLVED`
- Evidence: `line_identity_adapter.test.ts`; `verification-receipt.md`
- Resolution: Apply response is presented only as an accepted revocation request. `completed`／`manual_completed`
  values in the Apply payload cannot produce completion wording; only the subsequent binding/request re-query may
  establish the observed state.

## F-07 — Integrated Phase 4 query surfaces

- Status: `OPEN_SCOPE_ATTRIBUTION`
- Evidence: current `LineManagementPage.tsx` also composes later LINE Configuration query-only work.
- Disposition: do not remove the later bounded integration, but do not count Rich Menu／notification-rule query
  behavior as a Phase 3A deliverable. Its contract, tests and runtime evidence remain owned by its Phase 4 package.

# Phase 3A Verification Receipt

- Date: 2026-08-17 (fresh integration rerun)
- Branch/HEAD observed: `main@8615225481c8f72a9629289285516189b270cb36`
- Result: `STATIC_GATES_PASS_RUNTIME_BLOCKED`
- Runtime mutation evidence: not included in this receipt

## Focused frontend

Command:

```powershell
npm test -- src/tests/customer_service_client.test.ts src/tests/customer_service_adapter.test.ts src/tests/line_identity_client.test.ts src/tests/line_identity_adapter.test.ts src/tests/line_management_page_real_data.test.tsx src/tests/line_customer_service_resolve_flow.test.tsx src/tests/line_identity_revocation_flow.test.tsx src/tests/line_management_no_fake_mutation.test.tsx
```

Result: exit 0; 8 files, 53 tests passed.

## Focused backend

Command:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase3a-line-fixes -q tests/test_line_customer_service_first_release.py tests/test_customer_service_preview_contract.py tests/test_line_identity_management_first_release.py
```

Result: exit 0; 44 tests passed.

## Build and lint

- `npm run build`: exit 0; 81 modules transformed. Vite reports one existing chunk-size warning.
- `npm run lint`: exit 0; two existing Fast Refresh warnings in `MasterLayout.tsx`.

## Full frontend regression

Command: `npx vitest run --reporter=json`

Initial result: exit 1; 482 tests total, 470 passed, 12 failed. Fresh investigation proved two separate integration
regressions: Phase 2D tests had no volatile Session, and later presentation merge had removed the approved Phase 2B
Orders mutation surfaces while their tests remained. The owning integration scopes were repaired without weakening
strict decoders or zero-unexpected-network assertions.

First follow-up command: `npm test -- --reporter=dot`.

First follow-up result: exit 0; 35 files, 482 tests passed. Later integration added approved Phase 3A/4A query
coverage. A fresh 2026-08-17 full run exposed one test-harness leak: `orders_page_real_data.test.tsx` opened the
service-date drawer without mocking the approved `getServiceDates` query, allowing an unintended request to
`localhost:3000`. The test now injects the canonical service-date query fixture; production code was not changed.

Final command: `npm test`.

Final result: exit 0; **43 files, 510 tests passed**. No `ECONNREFUSED` or other unexpected network request appeared.
The run still emits React `act(...)` warnings in pre-existing route/race tests and the deliberate error output from
the ErrorBoundary crash test. These are not hidden and are tracked below; therefore this receipt does not claim a
warning-free frontend suite. `npm run build` passed with 94 modules transformed and one existing chunk-size warning.
`npm run lint` exited 0 with two pre-existing Fast Refresh warnings in `MasterLayout.tsx`.

## Static and source gates

- Strict UTF-8: 24 Phase 3A source/test files checked, 0 decode failures.
- Structured source headers: 24/24 present.
- Scoped trailing whitespace and `git diff --check`: passed.
- Phase 3A production/test scan: 0 `alert()`／`confirm()`／browser storage／`mockData`／forbidden Zod／skip markers.
- Phase 3A production scan: 0 direct `fetch()`／Axios／legacy customer PATCH／reply endpoint.
- Secret/PII scan: no committed credential or complete LINE identity was introduced into production display code.

## Independent audit corrections

Fresh audit found and Integration Owner corrected six issues before this receipt:

1. Pydantic optional-nullable fields now decode as `.nullable().optional()` and adapters normalize omission to `null`.
2. LINE identity client fails before network access when volatile Session is absent.
3. Identity Apply receipt followed by failed re-query remains `observation_failed`; it cannot return to Apply.
4. Unexpected Customer Service route errors map to a redacted typed internal 500 envelope.
5. LINE identity Apply now means only that the revocation request was accepted; completion wording is derived only
   from the subsequent binding/request re-query observation.
6. Customer Service ticket and event timestamps now use strict ISO datetime decoding and reject arbitrary strings.

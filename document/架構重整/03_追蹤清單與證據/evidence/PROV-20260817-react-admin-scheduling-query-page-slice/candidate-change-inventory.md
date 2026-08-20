# Candidate Change Inventory

## Production

- `api/routes/scheduling_current.py`：使用 enabled-principal `require_admin`；correlation header 由 Global middleware 注入／驗證。
- `ui_react/src/api/scheduling/scheduling_current_schemas.ts`
- `ui_react/src/api/scheduling/scheduling_current_errors.ts`
- `ui_react/src/api/scheduling/scheduling_current_client.ts`
- `ui_react/src/adapters/scheduling/scheduling_current_adapter.ts`
- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/SchedulingPage.css`

`api/schemas/scheduling_current.py` 經 fresh inspection 已 strict，未修改。Staff Query artifacts 只讀重用，未競寫。

## Tests／fixtures

- `tests/test_scheduling_current_router.py`
- `ui_react/src/tests/fixtures/scheduling/scheduling_current_contract_fixtures.ts`
- `ui_react/src/tests/scheduling_current_client.test.ts`
- `ui_react/src/tests/scheduling_current_adapter.test.ts`
- `ui_react/src/tests/scheduling_current_page.test.tsx`

## Boundary

- 0 DB/schema/migration/seed/backfill。
- 0 POST/PUT/PATCH/DELETE、0 provider/outbox/worker。
- 0 Staff file、shared transport/Auth、package/lockfile、其他 page 變更。


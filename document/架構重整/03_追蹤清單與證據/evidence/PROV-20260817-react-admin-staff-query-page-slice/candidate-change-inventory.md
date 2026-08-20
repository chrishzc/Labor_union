# Staff query page-slice candidate change inventory

Status: `complete`

Date: 2026-08-17

Scope: `#staff` bounded query-only page slice

## Production

- `api/routes/staff.py`：加入 `require_admin` 與互斥參數 typed 422；SQL/schema 不變。
- `ui_react/src/api/staff_directory/staff_directory_schemas.ts`
- `ui_react/src/api/staff_directory/staff_directory_errors.ts`
- `ui_react/src/api/staff_directory/staff_directory_client.ts`
- `ui_react/src/adapters/staff/staff_directory_adapter.ts`
- `ui_react/src/pages/StaffPage.tsx`
- `ui_react/src/pages/StaffPage.css`

## Tests／fixtures

- `tests/test_staff_summary_routes.py`
- `ui_react/src/tests/fixtures/staff/staff_directory_contract_fixtures.ts`
- `ui_react/src/tests/staff_directory_client.test.ts`
- `ui_react/src/tests/staff_directory_adapter.test.ts`
- `ui_react/src/tests/staff_directory_page.test.tsx`
- `ui_react/src/tests/staff_directory_no_fake_mutation.test.tsx`
- `ui_react/src/tests/staff_directory_request_budget.test.tsx`

## Boundary audit

- `api/schemas/staff_summary.py`：read-only，未修改。
- `ui_react/src/api/mockData.ts`：保留，未修改；StaffPage dependency closure 已移除 `MOCK_STAFF`。
- shared transport、Auth/session、Scheduling、其他 pages、package/lockfile、DB/schema/seed/migration：0 變更。
- Database change classes：schema-only 0、system-seed 0、business-row-backfill 0、destructive 0。

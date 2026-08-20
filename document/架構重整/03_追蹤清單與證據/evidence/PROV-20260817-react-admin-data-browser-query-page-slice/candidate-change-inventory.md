# Data Browser Query Page-Slice Candidate Inventory

## Backend

- `api/schemas/data_browser.py`
- `api/routes/data_browser_admin.py`
- `subsystems/access/data_browser_maintenance.py`
- `infrastructure/mysql/data_browser_query_repository.py`
- `tests/test_data_browser_admin_route.py` (read/verification input; no candidate edit)
- `tests/test_data_browser_query_contract.py`
- `tests/test_data_browser_privacy.py`

## React

- `ui_react/src/api/data_browser/data_browser_query_schemas.ts`
- `ui_react/src/api/data_browser/data_browser_query_errors.ts`
- `ui_react/src/api/data_browser/data_browser_query_client.ts`
- `ui_react/src/adapters/data_browser/data_browser_query_adapter.ts`
- `ui_react/src/pages/DataBrowserPage.tsx`
- `ui_react/src/tests/fixtures/data_browser/data_browser_query_contract_fixtures.ts`
- `ui_react/src/tests/data_browser_query_client.test.ts`
- `ui_react/src/tests/data_browser_query_adapter.test.ts`
- `ui_react/src/tests/data_browser_page_real_data.test.tsx`
- `ui_react/src/tests/data_browser_no_fake_mutation.test.tsx`
- `ui_react/src/tests/data_browser_request_budget.test.tsx`

`DataBrowserPage.css` required no change. No shared transport/Auth, package/lockfile, README/main plan, other page,
Streamlit, DB/schema/migration/seed/backfill, entry, worker/provider or Git operation is part of this candidate.

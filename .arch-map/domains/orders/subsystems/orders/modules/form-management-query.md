# Module: form-management-query

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
由案件及客戶目前資料提供唯讀表單情境與統計；補助市民為一般補助分類，社福為社福分類，不從舊名稱反推新政策。

## Implementation
- application: `subsystems/orders/form_management_query.py`
- adapter: `infrastructure/mysql/form_management_query_repository.py`
- dependency: `api/dependencies/form_management.py`
- transport: `api/routes/orders.py`

## Contracts
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` — CASESTAT 與現行身分映射。

## Verification
- layout_status: `custom_current`
- layout_basis: Existing bounded form-management query and isolated MySQL oracles remain at their original entrypoints.
- test_root: `tests/test_form_management_query.py`
- integration_root: `tests/test_form_management_query_disposable_mysql_e2e.py`

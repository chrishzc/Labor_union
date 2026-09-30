# Module: controlled-reopen

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
組成訂單受控重開的 Preview／fresh Apply，以 Order、Client Finance、Payroll current facts 驗證版本與預覽，並保存 command receipt。
Finance／Payroll version 可合法不存在；fresh presence 比較與取消後金融歷史檢查仍必須執行。

## Implementation
- primary:
  - `domains/orders/reopen.py`
  - `subsystems/orders/reopen_workflow.py`
  - `infrastructure/mysql/order_reopen_repository.py`
  - `api/schemas/order_reopen.py`
- entrypoints:
  - `api/routes/order_reopen.py`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/orders/subsystems/orders/integration/test_order_reopen_workflow.py`
- higher_boundary: `tests/domains/orders/subsystems/orders/integration/test_order_reopen_router.py`

## Provenance
- Controlled reopen workflow ownership — `source_observed` — `subsystems/orders/reopen_workflow.py` imports the Orders reopen rule, fresh-reads versions and persists the receipt; the direct workflow test exercises this owner.

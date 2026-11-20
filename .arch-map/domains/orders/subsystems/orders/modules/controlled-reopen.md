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

## Dependencies
- inbound: `scheduling/scheduling/matching-coordination` — 透過既有重開、取消與排班收據核對目前媒合資格；重開本身仍不恢復指派、等待鎖或排班。
- outbound: `scheduling/scheduling/matching-coordination` — fresh Apply 在同一 outer UoW 借既有 Matching repository 退役原有效推薦並追加取消事件；重播只回原收據。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/orders/subsystems/orders/integration/test_order_reopen_workflow.py`
- higher_boundary: `tests/domains/orders/subsystems/orders/integration/test_order_reopen_router.py`

## Provenance
- Controlled reopen workflow ownership — `source_observed` — `subsystems/orders/reopen_workflow.py` imports the Orders reopen rule, fresh-reads versions and persists the receipt; the direct workflow test exercises this owner.

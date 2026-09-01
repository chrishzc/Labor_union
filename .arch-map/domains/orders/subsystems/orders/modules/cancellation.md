# Module: cancellation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
組成訂單取消的 Query／Preview／Apply，驗證 fresh Orders、Scheduling、Client Finance 與 Payroll 根事實，並以單一交易產生取消 receipt／outbox。

## Implementation
- primary:
  - `domains/orders/cancellation.py`
  - `subsystems/orders/cancellation_workflow.py`
  - `infrastructure/mysql/order_cancellation_read_model.py`
  - `infrastructure/mysql/order_cancellation_repository.py`
- entrypoints:
  - `api/routes/order_cancellation.py`
  - `ui_react/src/api/orders/order_cancellation_client.ts`
  - `ui_react/src/pages/OrdersPage.tsx`

## Dependencies
- outbound: `scheduling/scheduling` — 取消有效 generation 與 assignment 重建。
- outbound: `client-finance/client-finance` — 取消退款／義務 impact。
- outbound: `payroll/payroll` — 服務人員薪資 impact。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — §3.5 cancellation 與 Preview／Apply typed errors。
- `/api/v1/orders/{case_no}/cancellation/{preview,apply}` — `api/routes/order_cancellation.py`。

## Verification
- static:
  - `.venv/bin/python -m pytest tests/domains/orders/subsystems/orders/integration/test_cancelled_order_reentry_guard.py tests/domains/orders/subsystems/orders/integration/test_order_cancellation_cross_domain_chain.py`
- higher_boundary: tests/domains/orders/subsystems/orders/integration/
- higher_boundary:
  - `ui_react/src/tests/orders_page_real_data.test.tsx`

## Provenance
- Cancellation workflow ownership — `architecture_declared` — Orders §3.5 and existing Orders subsystem map.
- Already-effective cancellation must be rejected before candidate rebuild — `source_observed` — `subsystems/orders/cancellation_workflow.py` and Orders UI contract.

## Change triggers
- 取消 eligibility／typed error、cross-domain impact、transaction owner、API entrypoint 或 UI cancellation gating 改變時重新 reconcile。

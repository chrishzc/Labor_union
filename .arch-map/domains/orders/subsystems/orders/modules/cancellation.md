# Module: cancellation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
組成訂單取消的 Query／Preview／Apply，驗證 fresh Orders、Scheduling、Client Finance 與 Payroll 根事實，並以單一交易產生取消 receipt／outbox。
合法不存在的下游 owner 以 NULL 表達；專用 reader 驗證 partial roots／孤立財務歷史。零服務案件若收取違約金且正式條件齊備，同一交易初始化必要的 Client Finance 主檔與款項。日期-only 開始日不代表已服務。
Query 依注入的台北業務日期排除未來排班，人員核對當日是否服務；未鎖定服務資料可確認為零日。取消及退款／補收全額核銷更新人工 LINE 通知資格，由人員預覽後發送。既有 terminal menu handoff 保留。

## Implementation
- primary:
  - `domains/orders/cancellation.py`
  - `subsystems/orders/cancellation_workflow.py`
  - `infrastructure/mysql/order_cancellation_read_model.py`
  - `infrastructure/mysql/order_cancellation_repository.py`
  - `api/schemas/order_cancellation.py`
  - `api/dependencies/order_cancellation.py`
- entrypoints:
  - `api/routes/order_cancellation.py`
  - `ui_react/src/api/orders/order_cancellation_client.ts`
  - `ui_react/src/components/OrderCancellationPanel.tsx`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Dependencies
- outbound: `scheduling/scheduling` — 取消有效 generation 與 assignment 重建。
- outbound: `client-finance/client-finance` — 取消退款／義務 impact。
- outbound: `payroll/payroll` — 服務人員薪資 impact。
- outbound: `government-subsidy/government-subsidy` — 已保存取消狀態與實際結束日後，在原 outer UoW 委派既有補助金額同步；保留整期快照，另列更正差額。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — §3.5 cancellation 與 Preview／Apply typed errors。
- `/api/v1/orders/{case_no}/cancellation/{preview,apply}` — `api/routes/order_cancellation.py`。
- 正式取消視窗先讀全案結算預覽，再由人員確認 Apply。Client Finance 在既有交易關卡建立一般退款或調整款，案件帳務以正式結算識別回讀，銀行核銷沿各原 owner。

## Verification
- layout_status: custom_current
- test_root: `tests/domains/orders/subsystems/orders/modules/cancellation/`
- static:
  - `.venv/bin/python -m pytest tests/domains/orders/subsystems/orders/modules/cancellation/ tests/domains/orders/subsystems/orders/integration/test_cancelled_order_reentry_guard.py tests/domains/orders/subsystems/orders/integration/test_order_cancellation_cross_domain_chain.py`
- disposable_mysql: `tests/test_historical_mid_service_cancellation_disposable_mysql_e2e.py`
- disposable_mysql: `tests/domains/orders/subsystems/orders/integration/test_order_cancellation_absent_roots_disposable_mysql.py`
- higher_boundary: tests/domains/orders/subsystems/orders/integration/
- higher_boundary:
  - `ui_react/src/tests/orders_page_real_data.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_cancellation.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_reopen.test.tsx`
- test_root: `ui_react/src/tests/order_cancellation_client.test.ts`

## Provenance
- Cancellation workflow ownership — `architecture_declared` — Orders §3.5 and existing Orders subsystem map.
- Already-effective cancellation must be rejected before candidate rebuild, except a historical cancellation-origin row with confirmed service-day facts entering its one-time canonical remediation path — `source_observed` — `subsystems/orders/cancellation_workflow.py` and Orders historical-remediation tests.

## Change triggers
- 取消 eligibility／typed error、cross-domain impact、transaction owner、API entrypoint 或 UI cancellation gating 改變時重新 reconcile。

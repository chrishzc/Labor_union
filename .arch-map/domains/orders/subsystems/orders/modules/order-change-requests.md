# Module: order-change-requests

## Parent

- domain: `orders`
- subsystem: `orders`

## Responsibility

擁有客戶訂單異動申請的快照、提交冪等、待處理／已結案狀態及經辦結果。工會從對應業務入口執行正式異動。

## Implementation

- `domains/orders/order_change_request.py`
- `subsystems/orders/order_change_requests.py`
- `infrastructure/mysql/customer_order_change_repository.py`
- `db/schema_parts/1077_order_change_requests.sql`
- `api/routes/line_order_change.py::admin_router`
- `ui_react/src/api/orders/order_change_requests_client.ts`
- `ui_react/src/components/OrderChangeRequestsPanel.tsx`
- `ui_react/src/components/OrderChangeRequestsPanel.css`
- `ui_react/src/pages/OrderWorkbenchV2Page.tsx`、`ui_react/src/components/OrderWorkbenchV2Drawer.tsx` — 待處理案件入口與個案申請歷程。

## Contracts

- `document/架構重整/01_規格基線/01_Orders_Domain.md`
- 管理端沿訂單管理能力列出待處理清單或指定案件歷程。僅有效人員 Session 可帶入版本與結果結案。
- 歷史客服工單來源以原 LIFF 事件命名空間及固定案號標頭查對。只讀出工單、事件及時間識別。

## Verification

- test_root: `tests/domains/orders/subsystems/orders/modules/order-change-requests/`
- inbound: `external-integration/line/customer-order-change-intake` — 驗證 LIFF 本人身分及訂單，沿單一交易提交。

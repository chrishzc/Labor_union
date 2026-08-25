---
doc_type: work-package
declared_status: completed
identity: PROV-20260822-react-admin-orders-cursor-continuation-successor
date: 2026-08-22
owner: Orders / React Integration Owner
domain: Orders
authority: latest-explicit-human-operations-frontend-priority
db_change: none
---

# Orders／Order Tracker cursor continuation successor

## Business scenario

工會人員使用真實資料時，Orders summaries可能超過首個bounded page。`#orders`與`#order-tracker`必須依server
`next_cursor`發送`after_case_no`續頁、追加且依case number去重；不得只顯示第一頁而宣稱可操作。

## Scope與不變量

- write set：`OrdersPage.tsx`、`OrderTrackerPage.tsx`及各自focused UI tests。
- 初始Query、explicit next page、retry各自維持bounded request；同cursor pending不得重送。
- unmount／initial reload終止續頁；失敗保留已載入資料並提供typed／明確錯誤，不顯示假完成。
- stage projection與summary使用相同cursor；mutation、API public contract、DB、entry switch與production host皆不在範圍。

## 驗收結果

- Orders pagination UI：`orders_page_real_data.test.tsx` 8 PASS。
- OrderTracker pagination UI：`order_tracker_real_data.test.tsx` 4 PASS；相鄰Tracker 4 files／12 PASS。
- Orders較廣focused regression：9 files／66 PASS；production build PASS。
- 本機fixture gate PASS；`lu_test_*`真引擎/API/browser與工會主機真實資料均尚未執行。

DB gate：Scope／Change inventory `PASS`（0 DB）；其餘`NOT_RUN`，結論`DB_CHANGE_NOT_READY`。

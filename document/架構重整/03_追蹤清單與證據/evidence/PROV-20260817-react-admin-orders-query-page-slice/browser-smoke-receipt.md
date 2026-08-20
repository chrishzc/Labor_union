# Orders Query Page-Slice Browser Smoke Receipt

狀態：`FAILED_PRE_FIX / AWAITING_BROWSER_RECHECK`。

2026-08-17 真 Chrome 曾在 `#orders` 觀察到兩次相同 `GET /api/v1/orders/summaries`，兩次皆為 304；此結果違反 initial-once budget。第一次 pending-only 修正仍因 304 在 StrictMode 第二 effect 前完成而重送。最終候選對同 session／query 的成功 flight 保留 250 ms burst TTL，failure 立即清除；帶 AbortSignal 的個別呼叫旁路共享。StrictMode component test 與 fake-timer TTL test已證明單一 transport call及TTL後可重新請求，但不得取代 browser recheck。

待執行最小清單：

1. 登入時不得記錄帳密、TOTP 或 Bearer token。
2. 初始 `#orders` 只出現一次 `GET /api/v1/orders/summaries`。
3. Date Drawer 最多 detail、calendar-detail、actual-start 各一次；Phase 2B Service Dates 自己的 requests 另依既有 state machine。
4. Matching Drawer 最多 detail、assignment-plan 各一次；不存在 candidate/recommend/active/contact GET。
5. Contract Drawer最多 detail、terms、contract-completion 各一次；不存在 contract-signing GET。
6. Cancellation Drawer 0 query，顯示 unavailable，且驗收期間不得觸發任何 non-GET。
7. unsupported 七階段、簽回、退款、推薦 slots 均可見 unavailable sentinel。

Browser 完成前，本包不可標示 `query-real-data-validated`。

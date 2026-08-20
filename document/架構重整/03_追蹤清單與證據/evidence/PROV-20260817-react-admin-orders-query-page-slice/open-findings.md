# Orders Query Page-Slice Open Findings

| ID | Finding | Status／owner |
|---|---|---|
| `ORD-F-01` | 真 Chrome pre-fix 與 pending-only candidate 都發現 StrictMode initial summaries 送出兩次 304；250 ms success burst TTL 已修正 | AWAITING-RECHECK；Integration Owner 以同一 session 重跑 browser gate |
| `ORD-F-02` | compatibility stage mapper | RESOLVED；OrderTracker migration後已從summary與Tracker全部移除 |
| `ORD-F-03` | denied legacy `never` types | RESOLVED；OrderTracker migration後已從query schemas移除，0 production consumer |
| `ORD-F-04` | Vite bundle >500 kB advisory | EXISTING；不屬 Orders query contract，不阻塞本包 |
| `ORD-F-05` | Full suite Route Guard 測試有既有 `act(...)` warnings，lint 有兩個 MasterLayout fast-refresh warnings | EXISTING；不在 exact write set，測試與 lint exit 均為 0 |
| `ORD-F-06` | 並行 Scheduling build drift | RESOLVED-IN-INTEGRATION；最新 `npm run build` 101 modules PASS |

本包沒有新增欄位級 gap。缺少七階段、正式推薦、契約簽回、取消退款等 server projection 的 slots 均保持 visible unavailable；未因此擴張 backend、DB 或 mutation scope。

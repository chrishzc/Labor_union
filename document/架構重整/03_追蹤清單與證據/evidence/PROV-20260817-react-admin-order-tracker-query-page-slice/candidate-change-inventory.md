# Order Tracker query page-slice candidate inventory

Final source timestamp: `2026-08-17T12:00:40+08:00`；base `main@8615225481c8f72a9629289285516189b270cb36`。

| Path | Final SHA-256 | Disposition |
|---|---|---|
| `ui_react/src/adapters/orders/order_tracker_adapter.ts` | `7CF1AA408651DDE08E234385470FEFD745A91F2D34D03123FDAC2D1271F9A56C` | rewritten query-only adapter |
| `ui_react/src/pages/OrderTrackerPage.tsx` | `8CE37640BA2444385A671977DE03F3EA4BDECE3696409E0E779EFFB0E7DF09F6` | rewritten honest unavailable presentation |
| `ui_react/src/pages/OrderTrackerPage.css` | `2C38F0CB35FB6F3BEB9E90FBAA6E4CB7D4DC956E32160A240412CD6E445B3CFC` | scoped accessible workbench styles |
| `ui_react/src/tests/order_tracker_adapter.test.ts` | `6EC771D903C931B87513251EB3832CD5F53ACD8201EC2408A9838CFEEC994E50` | new no-derivation tests |
| `ui_react/src/tests/order_tracker_real_data.test.tsx` | `1F10CE97E6D49CE3286C7DCB501A2709F5D9F0C508F9CEC1335073AB8B05B0D3` | replaced stale fake-stage assertions |
| `ui_react/src/tests/order_tracker_request_budget.test.tsx` | `D2B82E1C691D42AF2CE15A31970E4B66E411B5DD7390B8D0AAF7AA660734C3A7` | new StrictMode/abort/stale/budget tests |

Zero modifications：`OrdersPage`、Orders query client/schema/errors、summary adapter、backend、shared、Auth、package/lock、DB、README、main plan。未stage、commit、push、reset、clean、stash或建立worktree。


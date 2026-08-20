# Phase 2A candidate change inventory

- Identity: `PROV-20260816-react-admin-phase2a-orders`
- Candidate: `main@ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922` plus current dirty worktree
- Existing dirty/untracked files were preserved; no reset/clean/stash/commit/push was performed.
- This repository did not have a clean pre-task worktree, so this receipt does not falsely attribute unrelated paths.

| Path | Responsibility | Current result |
|---|---|---|
| `ui_react/src/api/orders/order_query_schemas.ts` | Orders-local strict envelope and eight typed success schemas | strict object/date/time/range validation; no default/record/passthrough |
| `ui_react/src/api/orders/order_query_client.ts` | eight GET methods, current-memory token, AbortSignal | raw/cross-domain endpoints excluded |
| `ui_react/src/api/orders/order_query_errors.ts` | minimum bounded HTTP mapping | removed 304/retired/raw-payload inference and `as any` |
| `ui_react/src/adapters/orders/order_summary_adapter.ts` | summary presentation | preserves canonical status; no 7-stage inference |
| `ui_react/src/adapters/orders/order_detail_adapter.ts` | four Drawer view models | no date/finance/status formula; partial-query failure is explicit |
| `ui_react/src/adapters/orders/order_tracker_adapter.ts` | seven-stage/SOP/notification presentation | dynamic facts unavailable; presentation labels retained |
| `ui_react/src/pages/OrdersPage.tsx` | real query wiring and UI slot preservation | AbortController; four Drawers; mutation controls locked |
| `ui_react/src/pages/OrderTrackerPage.tsx` | real summary query and Tracker shell | abort cleanup; 7 sections/11 rows/2 tabs retained |
| five Phase2A test files | strict client/adapter/page/no-fake tests | focused 44/44 pass |
| Phase2A specification/WP/index/evidence | current governance | status blocked only by G5 |

## Boundaries

- Backend, DB/schema, package/lockfile, Auth, Streamlit and the other business pages were not changed by this remediation.
- Phase 2B documents are proposed governance artifacts only; no Phase 2B production mutation was implemented.

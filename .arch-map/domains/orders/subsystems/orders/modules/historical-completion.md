# Module: historical-completion

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
組合 Orders Step 11 所需的 Orders、Scheduling、Client Finance 與 Staff Payables fresh readback；Query 保持 read-only。當 fresh oracle 證明歷史服務天數完整且雙邊款項均真正結清時，另由 bounded Preview／Apply 在單一 outer UoW 內追加 canonical lifecycle event/outbox，將 Orders 從「歷史服務完成」推進為「歷史帳務完成」。

## Implementation
- primary:
  - `subsystems/orders/historical_completion_oracle.py`
  - `subsystems/orders/historical_completion_query.py`
  - `subsystems/orders/historical_completion_projector.py`
  - `subsystems/orders/historical_completion_apply.py`
  - `infrastructure/mysql/historical_completion_writer.py`
  - `infrastructure/mysql/historical_client_finance_completion_read_adapter.py`
  - `infrastructure/mysql/historical_orders_scheduling_completion_read_adapter.py`
- entrypoints:
  - `api/routes/historical_completion.py`
  - `api/dependencies/historical_completion.py`
  - `api/schemas/historical_completion.py`
  - `ui_react/src/api/orders/historical_completion_client.ts`
  - `ui_react/src/api/orders/historical_completion_schemas.ts`
  - `ui_react/src/components/HistoricalCompletionPanel.tsx`

## Dependencies
- outbound: `scheduling`、`client-finance`、`staff-payables` — Query 只讀各 owner typed current readback；Apply 鎖定並驗證 exact owner versions/source vector，不改寫這些 owner root。
- Staff Payables completion evidence accepts either canonical bank payout/allocation lineage or exact current historical payout projection/event/link lineage；Apply locks both lineage families before fresh re-read，且歷史流程只接受 `payable_to_staff` obligations。
- outbound: Orders canonical lifecycle writer — 追加 lifecycle event/outbox 並以 lifecycle version CAS 更新 Orders projection。
- inbound: Orders tracker — 顯示terminal projection與owner-specific referral，不提供generic resolve。

## Contracts
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-baseline-projector-work-packages.md` — HOB-E composition與UI boundary。
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md` — payment、owner settlement與Step 11分離。
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md` — 歷史帳務完成 Q/P/A、fresh settlement 與 fail-closed lifecycle transition。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-completion/`
- integration_root: `ui_react/src/tests/historical_completion.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/historical-completion.md`

## Provenance
- Orders Step 11 composition ownership — `architecture_declared` — current HOB-E package and live subsystem owner。
- API／React paths and focused tests — `source_observed` — current repository。
- Cross-owner Step 11 oracle／query／projector／API／Apply coverage remains at the Orders subsystem integration boundary declared by the parent map；React presentation另由既有focused test保護。

## Change triggers
Reconcile when Step 11 inputs、owner referral、terminal projection、Apply freshness/idempotency、lifecycle writer、React presentation or focused test roots change。

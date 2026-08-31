# Module: historical-completion

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
組合Orders Step 11所需的Orders、Scheduling、Client Finance與Staff Payables fresh readback；只產生read-only terminal projection與owner referral，不推定或改寫任一owner root。

## Implementation
- primary:
  - `subsystems/orders/historical_completion_oracle.py`
  - `subsystems/orders/historical_completion_query.py`
  - `subsystems/orders/historical_completion_projector.py`
- entrypoints:
  - `api/routes/historical_completion.py`
  - `api/dependencies/historical_completion.py`
  - `api/schemas/historical_completion.py`
  - `ui_react/src/api/orders/historical_completion_client.ts`
  - `ui_react/src/api/orders/historical_completion_schemas.ts`
  - `ui_react/src/components/HistoricalCompletionPanel.tsx`

## Dependencies
- outbound: `scheduling`、`client-finance`、`staff-payables` — 只讀各owner typed current readback。
- inbound: Orders tracker — 顯示terminal projection與owner-specific referral，不提供generic resolve。

## Contracts
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-baseline-projector-work-packages.md` — HOB-E composition與UI boundary。
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md` — payment、owner settlement與Step 11分離。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_completion.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/historical-completion.md`

## Provenance
- Orders Step 11 composition ownership — `architecture_declared` — current HOB-E package and live subsystem owner。
- API／React paths and focused tests — `source_observed` — current repository。
- Cross-owner Step 11 oracle／query／projector／API coverage remains at the Orders subsystem integration boundary declared by the parent map。

## Change triggers
Reconcile when Step 11 inputs、owner referral、terminal projection、React presentation or focused test roots change。

# Module: obligation-planning

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
計畫客戶各付款階段的 obligation、日期替換與唯一的客戶現金方向；未結清義務只改到期日不得建立應收或退款。

## Implementation
- primary: `domains/client_finance/obligation_planning.py`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — Client Finance direction 與未結清 obligation 規則。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Actual Start 重建未結清 Client Finance projection 與日期，不建立付款或收款事實。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_finance_cancellation_direction.py`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`

## Provenance
- Direction contract — `architecture_declared` — current Client Finance and Orders specifications.
- Source and focused test path — `source_observed` — current workspace.

## Change triggers
Reconcile when Client Finance direction mapping、open obligation replacement、Actual Start projection handoff或focused test location changes。

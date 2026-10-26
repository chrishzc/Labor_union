# Module: subsidy-advance-recovery-workbench

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
舊逐案銷帳已退役。客戶實際出款依當日整期政府涵蓋判定 subsidy_advance／subsidy_return；原 ledger 不改寫。Government Subsidy period Query 沿同一期案件與不可變出款／沖正紀錄彙總回收，不新增逐案銷帳狀態。

## Implementation
- payout policy: `domains/client_finance/subsidy_advance.py`
- funding adapter: `infrastructure/mysql/client_refund_reversal_repository.py`
- current presentation replacement: `ui_react/src/components/SubsidyAdvanceSettlementPanel.tsx`
- retained historical query: `api/routes/subsidy_advance_settlement.py` — GET 唯讀；POST 410。
- historical implementation: `domains/client_finance/subsidy_advance_settlement.py`、`subsystems/client_finance/subsidy_advance_settlement.py`、`infrastructure/mysql/subsidy_advance_settlement_repository.py`、`ui_react/src/api/client_finance/subsidy_advance_settlement_client.ts`。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md`
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- current period owner: `.arch-map/domains/government-subsidy/subsystems/government-subsidy/modules/period-reconciliation.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/subsidy-advance-recovery-workbench/`
- integration_root: `tests/test_client_subsidy_advance.py` — 既有純政策入口保留，所有月份到期規則更新；舊 recovery helper 僅歷史證據。
- presentation_test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/subsidy-advance-recovery-workbench/`
- cross-owner current oracle routes to Government Subsidy `period-reconciliation`; that owner retains its integration tests.

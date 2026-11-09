# Module: subsidy-advance-recovery-workbench

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
舊逐案銷帳已退役。客戶實際出款依當日整期政府涵蓋判定 subsidy_advance／subsidy_return；原 ledger 不改寫。Government Subsidy period Query 沿同一期案件與不可變出款／沖正紀錄彙總回收，不新增逐案銷帳狀態。

## Implementation
- payout policy: `domains/client_finance/subsidy_advance.py`
- refund settlement: `domains/client_finance/client_refund_reversal.py`、`subsystems/client_finance/client_refund_reversal_workflow.py` — 補助退還與代墊共用既有 100 元內手續費規則；超過100元須明確選擇部分退款，保留原義務餘額。資金資格沿原正式到期日，不以後續服務日期重推。台新單筆／合併退款支援明選超退，沿同一 owner 建立一筆追償，完整原義務集合由ledger allocations追溯；ledger 保留銀行實付，Preview／fresh Apply 同源。
- funding adapter: `infrastructure/mysql/client_refund_reversal_repository.py` — 台新補助出款於Query／Preview／Apply以原始備註六碼經正式虛擬帳號解析確認案件，月嫂姓名優先，不要求帳號快照；一般退款及其他銀行仍沿帳戶驗證。
- current presentation: 由 Government Subsidy `SubsidyPeriodWorkbench.tsx` 整期直接處理，原逐案面板已退役清理。
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

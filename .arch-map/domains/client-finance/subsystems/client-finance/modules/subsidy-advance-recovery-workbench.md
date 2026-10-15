# Module: subsidy-advance-recovery-workbench

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
呈現正式工會補助墊款及政府 receipt allocation 的回收工作清單；人工 Preview／Apply 沿用既有 recovery 規則，建立不可變 settlement link，不新增客戶付款或政府 ledger。

## Implementation
- rules: `domains/client_finance/subsidy_advance_settlement.py`
- funding rule: `domains/client_finance/subsidy_advance.py`
- payout workflow: `subsystems/client_finance/client_refund_reversal_workflow.py`
- payout adapter: `infrastructure/mysql/client_refund_reversal_repository.py`
- payout preview client: `ui_react/src/api/client_finance/client_settlement_remediation_schemas.ts`
- shared case referral: `ui_react/src/components/CaseSubsidyDetailDrawer.tsx` — compact recovery timeline／QPA；單案精確篩選與結果不明時保留明細。
- primary: `subsystems/client_finance/subsidy_advance_settlement.py`
- existing recovery: `subsystems/client_finance/subsidy_advance_recovery.py`
- adapter: `infrastructure/mysql/subsidy_advance_settlement_repository.py`
- composition: `api/dependencies/subsidy_advance_settlement.py`
- schema: `api/schemas/subsidy_advance_settlement.py`
- entrypoint: `api/routes/subsidy_advance_settlement.py`
- registration: `api/main.py`
- presentation: `ui_react/src/components/SubsidyAdvanceSettlementPanel.tsx`
- client: `ui_react/src/api/client_finance/subsidy_advance_settlement_client.ts`
- page: `ui_react/src/pages/FinancePage.tsx`
- styles: `ui_react/src/pages/FinancePage.css`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — ADVREC-01～05；一般補助退款核銷與銀行匯入共用 owner funding 判斷，同一 payout 形成墊款，不建立重複退款。
- outbound: Government Subsidy immutable receipt allocation／outbox、batch version；Client Finance advance／entitlement／account version。
- existing automatic consumer: `subsystems/government_subsidy/subsidy_advance_outbox_consumer.py`。

## Verification
- layout_status: `custom_current`
- layout_basis: Python owner tests follow the canonical module root; React tests follow the same owner path within the existing ui_react Vitest discovery root.
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/subsidy-advance-recovery-workbench/`
- presentation_test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/subsidy-advance-recovery-workbench/`

## Change triggers
人工回收契約、來源 linkage、版本、冪等、入口或測試歸屬改變時重核。

# Module: statement-workspace

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
以正式入帳證據與 canonical 原列投影成功明細；獨立保存最小人工明細、identity-only 判重及跨人員警示解除。組合 Client Finance／Staff Payables typed case queries；不重算應收／薪資、不寫 ledger／allocation、不派送外部服務。

台新成功證據同時承接 Government Subsidy 既有 allocation 與現行整期 entry/member，沿用正式核銷與沖正的案件關聯。

月份查詢組合各 owner 正式到期款與已提交銀行事實；銀行來源單筆只計一次，人工原始明細不列現金，歷史案件標記整案排除統計。跨統計範圍而無正式分配金額的銀行款不拆算，現金結果回 unavailable/null，到期款查詢可繼續。案件歷史人工核銷僅寫 application metadata，保存當下原金額快照、原因、人員與時間，不改 owner 金額或 Orders。

## Implementation
- `domains/finance_import/statement_archive.py`
- `subsystems/finance_import/statement_archive.py`
- `subsystems/finance_import/accounting_workspace.py`
- `subsystems/finance_import/monthly_accounting.py`
- `infrastructure/mysql/monthly_accounting_repository.py`
- `infrastructure/mysql/finance_statement_archive_repository.py`
- `infrastructure/mysql/accounting_workspace_repository.py`
- `api/routes/finance_statement_workspace.py`
- `api/routes/finance_import.py` — composed router and existing bank commands
- `api/dependencies/finance_import.py`
- `api/schemas/finance_import.py`
- `ui_react/src/api/finance_import/finance_accounting_client.ts`
- `ui_react/src/api/finance_import/monthly_accounting_client.ts`
- `ui_react/src/components/FinanceMonthlyAccounting.tsx`、`FinanceMonthlyAccounting.css`
- `ui_react/src/components/FinanceReceivableItems.tsx` — 按到期月份列出正式應收款，未定日期款分到待確認；同一 typed Query 不建立第二份案件總額。
- `ui_react/src/components/HistoricalAccountingMarkerPanel.tsx`
- `ui_react/src/pages/FinancePage.tsx` — 收付款、案件帳務、銀行對帳、逾期提醒；舊查證工具保留可達入口。
- `ui_react/src/api/finance_import/finance_import_query_schemas.ts`
- `ui_react/src/components/FinanceCaseAccounting.tsx`
- `ui_react/src/components/FinanceCaseAccounting.css`
- `ui_react/src/components/FinanceStatementArchive.tsx`
- `db/schema_parts/235_finance_statement_workspace.sql`
- `db/schema_parts/1057_finance_statement_workspace.sql`
- `db/schema_parts/241_finance_case_accounting_markers.sql`、`db/schema_parts/1063_finance_case_accounting_markers.sql`

## Contracts
- `document/架構重整/01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md` §15
- archive endpoints: `statements/export`, `statements/manual`, `statements/duplicates` beneath `/api/v1/finance-import`
- case/warning endpoints: `cases/{case_no}/accounting`, `cases/{case_no}/accounting/dismiss`, `accounting/warnings`
- monthly endpoints: `accounting/monthly`、`accounting/monthly/export`；marker Query/Apply: `cases/{case_no}/accounting/historical-marker`。
- `accounting/receivables` — readonly 到期月份／全部月份／未定日期清單；沿用分類及歷史標記統計排除。
- marker Apply fresh-locks current owner versions, preserves an immutable amount snapshot, and supports same-key/same-command replay; one application transaction, no cash or service completion effect.
- archive command owns its outer transaction and same-command receipt; acknowledgement fresh-locks owner facts and checks existing version/amounts, writing only acknowledgement.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_workspace.py`
- Higher-boundary MySQL coverage uses the finance-import Subsystem's declared disposable E2E entry.
- test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/`

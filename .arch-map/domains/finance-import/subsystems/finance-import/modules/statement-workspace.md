# Module: statement-workspace

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
以正式入帳證據與 canonical 原列投影成功明細；獨立保存最小人工明細、identity-only 判重及跨人員警示解除。組合 Client Finance／Staff Payables typed case queries；不重算應收／薪資、不寫 ledger／allocation、不派送外部服務。

台新成功證據同時承接 Government Subsidy 既有 allocation 與現行整期 entry/member，沿用正式核銷與沖正的案件關聯。

## Implementation
- `domains/finance_import/statement_archive.py`
- `subsystems/finance_import/statement_archive.py`
- `subsystems/finance_import/accounting_workspace.py`
- `infrastructure/mysql/finance_statement_archive_repository.py`
- `infrastructure/mysql/accounting_workspace_repository.py`
- `api/routes/finance_statement_workspace.py`
- `api/routes/finance_import.py` — composed router and existing bank commands
- `api/dependencies/finance_import.py`
- `api/schemas/finance_import.py`
- `ui_react/src/api/finance_import/finance_accounting_client.ts`
- `ui_react/src/api/finance_import/finance_import_query_schemas.ts`
- `ui_react/src/components/FinanceCaseAccounting.tsx`
- `ui_react/src/components/FinanceCaseAccounting.css`
- `ui_react/src/components/FinanceStatementArchive.tsx`
- `db/schema_parts/235_finance_statement_workspace.sql`
- `db/schema_parts/1057_finance_statement_workspace.sql`

## Contracts
- `document/架構重整/01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md` §15
- archive endpoints: `statements/export`, `statements/manual`, `statements/duplicates` beneath `/api/v1/finance-import`
- case/warning endpoints: `cases/{case_no}/accounting`, `cases/{case_no}/accounting/dismiss`, `accounting/warnings`
- archive command owns its outer transaction and same-command receipt; acknowledgement fresh-locks owner facts and checks existing version/amounts, writing only acknowledgement.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_workspace.py`
- Higher-boundary MySQL coverage uses the finance-import Subsystem's declared disposable E2E entry.
- test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/`

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
- `ui_react/src/pages/FinancePage.tsx` — 進行中案件（預設）、銀行對帳、政府補助清單、每月帳務；所有案件入口開同一右側抽屜，原核銷與查證工具保留可達入口。
- `ui_react/src/components/FinanceCaseList.tsx` — 組合完整 Orders 搜尋及十三階段正式投影，第8步起列入，最多四案並行查詢；六欄／單一目前事項／階段時效篩選／20案分頁。沿Domain collection_progress顯示訂金→第一期→第二期→人工方案；只有客戶款齊且獨立人工方案已保存才移出。發出提醒共用LINE同案期款來源及原成功紀錄。
- `ui_react/src/components/FinanceBankReconciliationWorkspace.tsx`、`FinanceBankReconciliationWorkspace.css` — 銀行對帳工作台（WF-03/04），整合雙銀行匯入、待核對與已核銷總表、KPI膠囊統計及逐筆核對抽屜。
- `ui_react/src/components/FinanceGovernmentSubsidyList.tsx` — 僅接入 Reporting 既有共用畫面（週報補助統計／季度／年度與 XLSX）；政府補助唯一作業入口，案件仍開原抽屜並在原操作成功後重查報表，沒有內部 CSV 或第二套公式。
- `ui_react/src/api/finance_import/finance_import_query_schemas.ts`
- `ui_react/src/components/FinanceCaseAccounting.tsx`
- `ui_react/src/components/CaseDifferenceResolutionWorkbench.tsx` — 案件期款差額處置工作台；雙軌處置（直接銷帳／認列差額）與補繳／退補通知連動。
- `ui_react/src/components/FinanceCaseAccounting.css`
- `ui_react/src/components/FinanceCompactCase.css`
- `ui_react/src/components/FinanceSubsidyPlanForm.tsx` — explicit three-choice manual form; early save, CAS conflict, original-key unknown-result recovery and unsaved draft protection.
- `ui_react/src/components/FinanceStatementArchive.tsx`
- `db/schema_parts/235_finance_statement_workspace.sql`
- `db/schema_parts/1057_finance_statement_workspace.sql`
- `db/schema_parts/244_finance_case_arrangements.sql`、`db/schema_parts/1066_finance_case_arrangements.sql` — append-only arrangement events，case/version 與 operation key 唯一，UPDATE／DELETE 禁止。
- `db/schema_parts/241_finance_case_accounting_markers.sql`、`db/schema_parts/1063_finance_case_accounting_markers.sql`

- shared composition: `infrastructure/mysql/accounting_workspace_repository.py::build_accounting_workspace` — 案件、清冊與原 owner 退款同步共用 Client Finance 正式繳款來源。僅略過確認為零的缺席期款，工作台與補助交接使用同一應繳、實收結果，既有金融歷史衝突保留。

- `db/schema_parts/245_finance_case_subsidy_plans.sql`、`db/schema_parts/1067_finance_case_subsidy_plans.sql` — independent append-only manual plan events, not financial mutations or historical arrangement backfill.

## Contracts
- `document/架構重整/01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md` §15、§17～18
- archive endpoints: `statements/export`, `statements/manual`, `statements/duplicates` beneath `/api/v1/finance-import`
- manual plan endpoints: GET/POST `cases/{case_no}/accounting/subsidy-plan`; server actor, plan version CAS and same-command replay under the Orders case identity lock, one outer metadata transaction. No collection, bank uniqueness or legacy direct-arrangement prerequisite; no financial/date writer or payable generation.
- case/warning endpoints: `cases/{case_no}/accounting`, `cases/{case_no}/accounting/dismiss`, `accounting/warnings`
- monthly endpoints: `accounting/monthly`、`accounting/monthly/export`；marker Query/Apply: `cases/{case_no}/accounting/historical-marker`。
- `accounting/receivables` — readonly 到期月份／全部月份／未定日期清單；沿用分類及歷史標記統計排除。
- marker Apply fresh-locks current owner versions, preserves an immutable amount snapshot, and supports same-key/same-command replay; one application transaction, no cash or service completion effect.
- archive command owns its outer transaction and same-command receipt; acknowledgement fresh-locks owner facts and checks existing version/amounts, writing only acknowledgement.

- case Query adds independent stage provenance, T/B/S, current collection gate and conservative scheme projection; absent government money is never direct-arrangement evidence. Direct arrangement facts are explicit append-only confirm_direct/withdraw_direct events, never inferred from missing government cash; same-case GET/POST arrangement is the authenticated metadata writer, with arrangement version, Orders identity lock and original-command replay.
- arrangement confirmation fresh-reads the original paid-stage, T/B/S and bank facts; insufficient or contradictory sources reject confirmation. Later G/PT/RT or B/T conflicts leave the original arrangement intact and project scheme=unknown. History uses UTC ISO instants and Taipei display; formed service/due dates are untouched.
- bank facts add uniquely proven C/G/PS/PT/RS/RT; monthly by original bank date, single-case totals unavailable for shared sources. Existing ledgers, allocations and due/service dates are read-only.
- case drawer uses a compact identity/date/total summary and four independently collapsible same-page blocks: customer periods (with difference resolution workbench), manual subsidy plan, staff payables (with 100 NTD fee settlement notes and payout history), and client refunds & government subsidy flows. Posted receipt information comes only from the original allocation Query; no case-side bank reconciliation, duplicate cash/history sections or current-item strip. Notification subview is owned by LINE payment-overdue-reminders; bank/monthly/payable tools keep their original writers.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_workspace.py`
- Higher-boundary MySQL coverage uses the finance-import Subsystem's declared disposable E2E entry.
- test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/`

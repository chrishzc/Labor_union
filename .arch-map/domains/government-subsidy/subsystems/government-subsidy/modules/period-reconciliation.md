# Module: period-reconciliation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
月／季／年共用有效服務結束月份與補助公式，整期金額核對銀行事實；季度涵蓋月份、跨單位／移期防重、追加整期沖正。案件快照只作證據，不拆造逐案入款。工會代墊回收直接依同一期的既有實付與沖正紀錄彙總。

## Implementation
- 銀行待核對批次重配透過既有整期 repository 讀取月／季／年候選，唯一金額吻合才於 Finance Import outer UoW 委派整期核銷。
- difference adapter: `infrastructure/mysql/government_period_difference_repository.py`; original receipt/member snapshot frozen at first partial payment, supplemental receipt/refund/loss and separate case corrections; amount controls consume canonical formula, never allocate government cash to cases.
- schema: `db/schema_parts/242_accounting_difference_resolution.sql`, `db/schema_parts/1064_accounting_difference_resolution.sql` (shared release, owner-specific tables).
- domain: `domains/government_subsidy/period_reconciliation.py`
- application: `subsystems/government_subsidy/period_reconciliation.py`
- adapter: `infrastructure/mysql/government_subsidy_period_repository.py`
- `query_case_subsidy_amount` — 依單案原來源與有效人工金額控制投影 S；不受報表選案狀態、方案或退款義務是否存在影響。Finance workspace、名冊／訂單匯出與 case coverage 共用，零寫入且保留未知。
- shared source/formula: `subsystems/government_subsidy/reconciliation_register_query.py`
- API: `api/routes/government_subsidy_periods.py`
- presentation: `ui_react/src/components/SubsidyPeriodWorkbench.tsx`
- client: `ui_react/src/api/government_subsidy/period_reconciliation_client.ts`
- composition: `ui_react/src/components/FinanceReceiptsWorkspace.tsx`、`ui_react/src/components/OrderGovernmentSubsidyLane.tsx`
- schema: `db/schema_parts/233_government_subsidy_periods.sql`、`db/schema_parts/1055_government_subsidy_periods.sql`

## Contracts
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- Client Finance 出款不可變，期款不重付；年度 version 與來源／bank fresh locks，同一 application 單次 outer commit。
- Finance Import 政府流水保留待選期間；核銷後標為已消費，不能再人工更正到其他 owner。
- 原整期save後沿同一outer UoW借用Client Finance正式同步；只在共用案件Query確認本案客戶先墊後退及正式S時成立客戶應退，不由member快照拆造逐案政府現金，不增加commit或新銀行writer。

## Verification
- integration_root: `tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_differences_mysql.py`
- layout_status: `custom_current`
- layout_basis: Python rules use the canonical module root; the existing React Vitest discovery root mirrors the same owner path.
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/period-reconciliation/`
- integration_root: `tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_reconciliation_mysql.py`
- presentation_test_root: `ui_react/src/tests/domains/government-subsidy/subsystems/government-subsidy/modules/period-reconciliation/`
- focused: `test_period_reconciliation.py`、`test_period_reconciliation_mysql.py`

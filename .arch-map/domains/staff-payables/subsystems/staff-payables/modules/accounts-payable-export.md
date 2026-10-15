# Module: accounts-payable-export

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
依一致性快照彙整月嫂應付與客戶退款／補助退回；對已採納完成、但尚無 materialized service-pay obligation 的既有歷史訂單，以最新歷史天數或 Orders 原服務天數做唯讀 fallback 投影。產生會計 XLSX，下載與封存使用同一份位元組，不執行付款或在 Query 時寫 DB。
同一 reporting owner 提供已排班案件的資金需求唯讀投影；保留未知金額／日期及受款資料待確認項目，未建客戶補助退款單時沿用 Client Finance 規則預估，不修改帳務或付款。

## Implementation
- primary: `subsystems/staff_payables/accounts_payable_export.py`
- composition: `api/dependencies/accounts_payable_export.py`
- api-schema: `api/schemas/accounts_payable_export.py`
- source: `infrastructure/mysql/accounts_payable_export_sources.py`
- archive: `infrastructure/archive/accounts_payable.py`
- cash planning: `subsystems/staff_payables/cash_requirements_query.py`
- cash planning source: `infrastructure/mysql/cash_requirements_repository.py`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — §2.5、§2.5.1。
- `api/routes/finance_reports.py` — accounts-payable query/export。
- `api/routes/finance_reports.py` — authenticated bounded `/accounts-payable/cash-requirements` GET；既有 query/export 與付款入口不變。

## Dependencies
- outbound: `orders/orders/module:historical-service-accounting` — 只讀最新歷史天數 revision；缺少時回退 Orders 原服務天數。
- outbound: `payroll/historical-service-accounting` — 沿用 assignment rate snapshot、單薪與樓層費計算，不重定義 Payroll 規則。
- outbound: `client-finance/client-finance/module:client-subsidy-return-query` — 沿用 Domain `project_subsidy_return` 與補助到期日規則，只將目前排班結束日作為明示預估日期來源。

## Verification
- 使用父 Subsystem index 已宣告的 integration_root；匯出快照與模板測試由該跨來源整合邊界持有。

## Provenance
- 匯出、資料來源與封存實作 — source_observed — 上述 Implementation。

## Change triggers
來源篩選、彙整、Excel 格式或下載／封存契約變更。

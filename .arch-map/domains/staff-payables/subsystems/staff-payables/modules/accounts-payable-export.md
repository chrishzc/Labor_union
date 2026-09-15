# Module: accounts-payable-export

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
依一致性快照彙整月嫂應付、客戶退款／補助退回及政府溢付款退回；對已採納完成、但尚無 materialized service-pay obligation 的既有歷史訂單，以最新歷史天數或 Orders 原服務天數做唯讀 fallback 投影。產生會計 XLSX，下載與封存使用同一份位元組，不執行付款或在 Query 時寫 DB。

## Implementation
- primary: `subsystems/staff_payables/accounts_payable_export.py`
- composition: `api/dependencies/accounts_payable_export.py`
- api-schema: `api/schemas/accounts_payable_export.py`
- source: `infrastructure/mysql/accounts_payable_export_sources.py`
- archive: `infrastructure/archive/accounts_payable.py`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — §2.5。
- `api/routes/finance_reports.py` — accounts-payable query/export。

## Dependencies
- outbound: `orders/orders/module:historical-service-accounting` — 只讀最新歷史天數 revision；缺少時回退 Orders 原服務天數。
- outbound: `payroll/historical-service-accounting` — 沿用 assignment rate snapshot、單薪與樓層費計算，不重定義 Payroll 規則。

## Verification
- 使用父 Subsystem index 已宣告的 integration_root；匯出快照與模板測試由該跨來源整合邊界持有。

## Provenance
- 匯出、資料來源與封存實作 — source_observed — 上述 Implementation。

## Change triggers
來源篩選、彙整、Excel 格式或下載／封存契約變更。

# Module: accounts-payable-export

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
依一致性快照彙整月嫂應付、客戶退款／補助退回及政府溢付款退回；產生會計 XLSX，下載與封存使用同一份位元組，不執行付款。

## Implementation
- primary: `subsystems/staff_payables/accounts_payable_export.py`
- composition: `api/dependencies/accounts_payable_export.py`
- source: `infrastructure/mysql/accounts_payable_export_sources.py`
- archive: `infrastructure/archive/accounts_payable.py`

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — §2.5。
- `api/routes/finance_reports.py` — accounts-payable query/export。

## Verification
- 使用父 Subsystem index 已宣告的 integration_root；匯出快照與模板測試由該跨來源整合邊界持有。

## Provenance
- 匯出、資料來源與封存實作 — source_observed — 上述 Implementation。

## Change triggers
來源篩選、彙整、Excel 格式或下載／封存契約變更。

# Module: accounts-payable-export

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
依一致性快照彙整正式月嫂應付與客戶退款／補助退回；歷史案件也只讀相同 Payroll obligation 及其 assignment binding，缺少義務時明示缺件，不在 Query 重算一份歷史薪資或建立假 obligation identity。產生會計 XLSX，下載與封存使用同一份位元組，不執行付款或在 Query 時寫 DB。
同一 reporting owner 提供已排班案件的資金需求唯讀投影；保留未知金額／日期及受款資料待確認項目，未建客戶補助退款單時沿用 Client Finance 規則預估，不修改帳務或付款。
同份月清冊的月嫂款項沿用該月 15 日；客戶一般退款及補助退款讀取月底以前仍未清償的款項，包含以前月份餘額及部分退款剩餘款，不重列已退金額。

## Implementation
- primary: `subsystems/staff_payables/accounts_payable_export.py`
- composition: `api/dependencies/accounts_payable_export.py`
- api-schema: `api/schemas/accounts_payable_export.py`
- source: `infrastructure/mysql/accounts_payable_export_sources.py`
- archive: `infrastructure/archive/accounts_payable.py`
- archive configuration: `api/dependencies/accounts_payable_export.py` reads `ACCOUNTS_PAYABLE_ARCHIVE_ROOT`; NAS `deployment/nas/compose.yaml` sets `/data/accounts-payable-archive` on the persistent app-data bind mount. Local installations without this setting retain `downloads/accounts_payable_archive`.
- cash planning: `subsystems/staff_payables/cash_requirements_query.py` — 付款統一清單來源，唯讀保留 staff_id 供逐人明細精確定位；金額與日期規則不變。
- cash planning source: `infrastructure/mysql/cash_requirements_repository.py`
  - 付款主清單保留已付／結清列，以獨立 `payment_status` 呈現 pending／partially_paid／paid／settled；包含 exact current 歷史確認及沖正後的目前餘額。匯出仍只選未付項目。

## Contracts
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md` — §2.5、§2.5.1。
- `api/routes/finance_reports.py` — accounts-payable query/export。
- `api/routes/finance_reports.py` — authenticated bounded `/accounts-payable/cash-requirements` GET；既有 query/export 與付款入口不變。

## Dependencies
- outbound: `orders/orders/module:historical-service-accounting` — 舊案缺義務轉介既有 Preview／Apply 補建，不代算或代寫。
- outbound: `payroll/historical-service-accounting` — 只讀該 owner 已建立的正式義務，不在報表重跑單薪／樓層費公式。
- outbound: `scheduling` — 與 Assignment Plan Query 共用 `order_terms_read_model.select_current_assignments`，不以 `orders.staff_id` 或任意最大 assignment id 代替 current binding。
- outbound: `client-finance/client-finance/module:client-subsidy-return-query` — 沿用 Domain `project_subsidy_return` 與補助到期日規則，只將目前排班結束日作為明示預估日期來源。

## Verification
- 使用父 Subsystem index 已宣告的 integration_root；匯出快照與模板測試由該跨來源整合邊界持有。

## Provenance
- 匯出、資料來源與封存實作 — source_observed — 上述 Implementation。

## Change triggers
來源篩選、彙整、Excel 格式或下載／封存契約變更。

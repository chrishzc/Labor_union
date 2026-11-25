# Module: accounts-payable-export

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
依一致性快照彙整正式月嫂應付與客戶退款／補助退回；歷史案件也只讀相同 Payroll obligation 及其 assignment binding，缺少義務時明示缺件，不在 Query 重算一份歷史薪資或建立假 obligation identity。產生會計 XLSX，下載與封存使用同一份位元組，不執行付款或在 Query 時寫 DB。
同一 reporting owner 提供已排班案件的資金需求唯讀投影；保留未知金額／日期及受款資料待確認項目，未建客戶補助退款單時沿用 Client Finance 規則預估，不修改帳務或付款。
同份月清冊的月嫂款項沿用該月 15 日；客戶一般退款及補助退款讀取月底以前仍未清償的款項，包含以前月份餘額及部分退款剩餘款，不重列已退金額。
依規格 #16A §3.3–3.4消費最後正式保存的人工方案；無新人工安排的歷史案件保留原來源。新案缺方案原則上待確認，但原owner已證明合法全額補助、服務結束且來源無衝突時，沿FULL例外承接月嫂正式未付餘額至台新，不冒充人工方案已保存。普通應付與一般退款不因補助單筆待確認而整案阻擋。清冊只讀既有正式款項，不因方案更正重建或改期。銀行沿 #16A §3.3；月嫂永豐／台新分列，正常客戶退款永豐、補助退款台新，月嫂姓名欄組合公會自訂編號。未知付款用途保留排除原因，不用舊分期標記另判三方案；既有退款與新方案衝突保留原記錄及原因。

## Implementation
- handoff rule: `domains/staff_payables/subsidy_handoff.py` — 規格 #16A §3.4；最後人工方案優先，正式服務結束、墊款依據與逐款衝突判定，不改寫金融根事實。
- primary: `subsystems/staff_payables/accounts_payable_export.py`
- composition: `api/dependencies/accounts_payable_export.py`
- api-schema: `api/schemas/accounts_payable_export.py`
- client: `ui_react/src/api/accounts_payable/accounts_payable_query_client.ts`、`ui_react/src/api/accounts_payable/accounts_payable_query_schemas.ts`
- source: `infrastructure/mysql/accounts_payable_export_sources.py`
- `_staff_funding_rows` 沿原 Staff Payables `query_staff_funding_portions` 的銀行別核銷連結讀取分期餘額；Payroll SQL 只列日期／帳戶等候選，不以總已付假定先付自備款。已付分期不重列，未知分配明示 blocked；同一投影供月清冊及逐案查核。
- archive: `infrastructure/archive/accounts_payable.py`
- archive configuration: `api/dependencies/accounts_payable_export.py` reads `ACCOUNTS_PAYABLE_ARCHIVE_ROOT`; installations without this setting default to `downloads/accounts_payable_archive`.
- cash planning: `subsystems/staff_payables/cash_requirements_query.py` — 付款統一清單來源，唯讀保留 staff_id 供逐人明細精確定位；金額與日期規則不變。
- cash planning source: `infrastructure/mysql/cash_requirements_repository.py`
  - 付款主清單保留已付／結清列，以獨立 `payment_status` 呈現 pending／partially_paid／paid／settled；包含 exact current 歷史確認及沖正後的目前餘額。匯出仍只選未付項目。

- shared composition: `infrastructure/mysql/accounting_workspace_repository.py::query_subsidy_payable_handoff` — 與案件查詢共用typed Client Finance funding及正式方案，清冊／cash planning不另算資格或S。

## Contracts
- [規格 #16A](../../../../../requirements/16A_Accounts_Payable_Export與現金需求清冊規格.md) §3.2–3.4、§4 是清冊的納入、來源及驗收規則；付款核銷本身仍由 #16 §2.2–2.3 管理。
- `FinanceMonthlyAccounting.tsx`：十欄應付帳款 Excel 是獨立入口，每次選一個出款月份，以 `target_month` 呼叫 `GET /api/v1/finance-reports/accounts-payable/export`；不沿用每月帳務摘要的查詢範圍或口徑。
- `GET /api/v1/finance-reports/accounts-payable` 的查詢與後續 XLSX 匯出各取新的唯讀快照。同一筆合格的月嫂款在原到期月份只列正式正數未付額，期間若已補款，新下載可正常反映更少或不列；不改原付款日或舊封存。客戶退款沿 #16A §3.2 的月底截止口徑，不套月嫂款規則。
- 一次成功匯出必須讓回傳與封存的 XLSX 共用相同 bytes 與 SHA-256；只寫封存檔，不寫義務、ledger 或發動匯款。封存失敗回可重試的 `503 accounts_payable_archive_failed`，不交付 XLSX。舊 `/accounts-payable-summary` 回 `410`，不再是清冊入口。
- `api/routes/finance_reports.py` — 歷史月嫂款可用案號、月嫂完整姓名或公會編號查未列入原因，讀取同一案件應付查核來源。
- `api/routes/finance_reports.py` — authenticated bounded `/accounts-payable/cash-requirements` GET；既有 query/export 與付款入口不變。

## Dependencies
- outbound: `payroll/payroll/module:payroll-adjustment` — 缺義務或正式未付款項更正轉介原 Payroll 流程。清冊查詢不代算或代寫。
- outbound: `payroll/historical-service-accounting` — 報表只讀既有正式義務。歷史逐案查核可用該 owner 的唯讀同步預覽取得目前缺件或歸屬待核對原因，預覽不填入清冊金額或日期。
- outbound: `scheduling` — 與 Assignment Plan Query 共用 `order_terms_read_model.select_current_assignments`，不以 `orders.staff_id` 或任意最大 assignment id 代替 current binding。
- outbound: `client-finance/client-finance/module:client-subsidy-return-query` — 沿用 Domain `project_subsidy_return` 與補助到期日規則，只將目前排班結束日作為明示預估日期來源。

## Verification
- 使用父 Subsystem index 已宣告的 integration_root；匯出快照與模板測試由該跨來源整合邊界持有。
- `tests/domains/staff-payables/subsystems/staff-payables/integration/test_accounts_payable_query_api.py` — 複核清冊／案件查核／XLSX 的餘額、重查後結清排除、零帳務提交，以及暫存封存檔與下載的 bytes 一致；測試使用替代 DB，不是銀行到清冊的端對端驗收。

## Provenance
- 匯出、資料來源與封存實作 — source_observed — 上述 Implementation。

## Change triggers
來源篩選、彙整、Excel 格式或下載／封存契約變更。

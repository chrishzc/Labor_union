# Module: obligation-planning

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
計畫客戶各付款階段的 obligation、日期替換與唯一的客戶現金方向；中途取消依已確認實際服務量重算，並依實際服務量同步獨立 subsidy-return payable。未結清義務只改到期日不得建立應收或退款。
尚未排班且 Scheduling root 不存在的取消，以明確零服務量計算既有訂金退款，不補造 Scheduling generation。
第二期有金額時，stage plan 預計繳款日由第一期預計入帳日加 15 個曆日計算；零金額不產生第二期日期。契約及訂單資訊重用此 owner 日期投影。
原已收期款取消歸零而產生退款時，若 stage plan 不再產生日期，退款保留原義務的到期日；不把既有已知退款日期清空，原本未知則保留待確認。
完整進件及計價條件保存時，在同一 outer UoW 自動同步訂金、第一二期及應退補助，不等待簽約、完工、收款齊全或人工建立付款義務。補助市民最高 40 小時先墊，社福最高 120 小時不先墊補助部分。日期／條件變動沿原 identity 更新，實付不可變；取消使用實際服務量。應退於有效服務結束月加兩月 15 日到期，所有月份適用。歷史分支保持 actual-service owner。

## Implementation
- subsidy policy: `domains/client_finance/subsidy_coverage.py` — canonical 補助市民 40／社福 120 小時，歷史來源別名不新增申請關卡。
- primary: `domains/client_finance/obligation_planning.py`
- calculation: `domains/client_finance/order_amount_calculation.py`
- adapter: `infrastructure/mysql/client_finance_terms_writer.py`
- automatic adapter: `infrastructure/mysql/automatic_client_accounting.py` — 沿 caller transaction，同步應付與應退補助；不 commit、不發送。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — Client Finance direction 與未結清 obligation 規則。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Actual Start 重建未結清 Client Finance projection 與日期，不建立付款或收款事實。
- cross-owner evidence: `tests/domains/orders/subsystems/orders/integration/test_order_cancellation_absent_roots_disposable_mysql.py` — deposit refund without Scheduling or Payroll, replay and controlled reopen; Orders owns this integration proof.

## Verification
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_automatic_accounting.py`
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_finance_cancellation_direction.py`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`

## Provenance
- Direction contract — `architecture_declared` — current Client Finance and Orders specifications.
- Source and focused test path — `source_observed` — current workspace.

## Change triggers
Reconcile when Client Finance direction mapping、open obligation replacement、Actual Start projection handoff或focused test location changes。

# Module: obligation-planning

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
計畫客戶各付款階段的 obligation、日期替換與唯一的客戶現金方向；中途取消依已確認實際服務量重算，並在客戶款已涵蓋實際應付時建立獨立 subsidy-return payable。未結清義務只改到期日不得建立應收或退款。
尚未排班且 Scheduling root 不存在的取消，以明確零服務量計算既有訂金退款，不補造 Scheduling generation。
第二期有金額時，stage plan 預計繳款日由第一期預計入帳日加 15 個曆日計算；零金額不產生第二期日期。契約及訂單資訊重用此 owner 日期投影。
正式 Finance writer 在期款建立／重算的同一交易同步 typed candidate 的付款條款及 immutable payment-terms event；第二期零金額保存 NULL。簽約前相關 Orders 條件變更使用只含預計 stage plans／付款條款異動的 candidate，actions 為空；第一期更新為新的開始日、訂金期限不晚於開始日，第二期由同一 owner 重新判定日期／NULL。日期異動納入 Finance 版本與同一 Terms Apply，不建立義務。

## Implementation
- primary: `domains/client_finance/obligation_planning.py`
- calculation: `domains/client_finance/order_amount_calculation.py`
- adapter: `infrastructure/mysql/client_finance_terms_writer.py`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — Client Finance direction 與未結清 obligation 規則。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Actual Start 重建未結清 Client Finance projection 與日期，不建立付款或收款事實。
- cross-owner evidence: `tests/domains/orders/subsystems/orders/integration/test_order_cancellation_absent_roots_disposable_mysql.py` — deposit refund without Scheduling or Payroll, replay and controlled reopen; Orders owns this integration proof.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_finance_cancellation_direction.py`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`

## Provenance
- Direction contract — `architecture_declared` — current Client Finance and Orders specifications.
- Source and focused test path — `source_observed` — current workspace.

## Change triggers
Reconcile when Client Finance direction mapping、open obligation replacement、Actual Start projection handoff或focused test location changes。

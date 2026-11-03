# Module: receipt-reconciliation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由 Client Finance 擁有案件專屬虛擬帳號的確定性產生／解析規則；匯入實際對照優先於公式候選，只有完全沒有匯入對照時才使用公式。驗證客戶收款與應收義務，並編排 fresh Preview／Apply、核銷分配與收據。一般核銷維持精確；人員明示部分收款時才保留實收與餘額，明示超收才沿既有退款義務流程。案件層級核對可不指定單一期款，按正式到期日排列選定義務，讓同案多筆合計跨期核銷；不放寬跨案件或重複銀行來源。部分收款不宣告訂金收足或發出該期收款完成通知；後續補足保留所有來源，訂金投影記累計分配，通知證據沿本次 settlement 的分配額。
等待訂金檔期釋放可借用原外層 UoW 的唯讀 `query_unreceived_deposit`：完整查核 account 版本、同案 obligations／義務事件／ledger，以 Domain-owned `UnreceivedDepositConfirmation` 提供未建立帳务且未收款證明；不因缺 settlement projection 推定零、不建立 account 或帳務根事實。

## Implementation
- difference owner: `domains/client_finance/difference_resolution.py`, `subsystems/client_finance/difference_resolution.py`, `infrastructure/mysql/client_difference_repository.py` — noncash loss/reduction/fee/absorption, state-only refund closure and original cash preservation; amount modes borrow original source writer.
- recovery cash adapter: `infrastructure/mysql/client_over_refund_recovery_repository.py` — existing Client Finance matched collection, preserves true amount/date/reference and returns the declared receipt contract; case/month query includes recovered cash separately from noncash dispositions.
- entrypoint: `api/routes/accounting_differences.py`; presentation: `ui_react/src/api/client_finance/difference_resolution_client.ts`, `ui_react/src/components/AccountingDifferencePanel.tsx`.
- `db/schema_parts/236_client_refund_overage_receipt.sql`, `db/schema_parts/1058_client_refund_overage_receipt.sql` — append the already-supported refund_overage kind to persistence receipts; preserve old enum ordinals and receipt rows.
- case accounting projection: `subsystems/client_finance/case_accounting_query.py`, `infrastructure/mysql/client_payments_query_repository.py` — current obligation events, signed allocations, explicit surplus disposition and valid historical evidence; query only, typed consumer in Finance Import workspace.
- primary:
  - `domains/client_finance/reconciliation.py`
  - `subsystems/client_finance/reconciliation_workflow.py`
  - `subsystems/client_finance/virtual_account_resolution.py`
  - `infrastructure/mysql/client_receipt_reconciliation_repository.py`
  - `subsystems/client_finance/first_payment_query.py`、`infrastructure/mysql/first_payment_query_repository.py` — typed current first-stage settlement Query; exact-zero, marked committed receipt, allocation and reversal checks, no writes.
  - `subsystems/client_finance/second_payment_query.py` — typed required-stage／settlement query；LINE 不重算入帳根事實。
  - `infrastructure/mysql/second_payment_query_repository.py`
  - `subsystems/client_finance/deposit_payment_query.py`
  - `infrastructure/mysql/deposit_payment_query_repository.py`
  - `subsystems/client_finance/overdue_payment_query.py` — 訂金／第一期／第二期各筆正式到期日與未核銷餘額的 typed 唯讀契約。
  - `infrastructure/mysql/overdue_payment_query_repository.py` — 依各筆 obligation 查詢，不跨期合計；Query 無寫入。
  - `subsystems/client_finance/payment_reminder_query.py`、`infrastructure/mysql/client_payment_reminder_query_repository.py` — typed current initial/reminder facts, unique required second stage, remaining balance, readonly current contract evidence and Orders start-date projection; no new payment state or writer.
- entrypoints:
  - `api/routes/client_receipt_reconciliation.py`
  - `api/schemas/client_receipt_reconciliation.py`
  - `ui_react/src/api/client_finance/client_receipt_reconciliation_client.ts`、`ui_react/src/components/ClientReceiptReconciliationPanel.tsx` — 案件頁同案入款與合計核對，精確／部分／超收正式 Preview/Apply；差額處理不預選。

## Dependencies
- outbound: `orders` — 各期逾期 Query 只讀同案正式契約完成事件與目前契約識別；雙方簽約完成才列入提醒清單與總數，預先計價與核銷不受影響。
- inbound: `finance-import` — 透過 owning-domain composite 委派收款核銷並保留外層交易。
- outbound: `orders` — 以已提交的 deposit intent 通知訂金核銷結果。
- outbound: `external-integration/line/order-pre-start-notification-source` — 第二期正式核銷在既有 projection_refresh payload 帶通知標記與正式金額／分配 identity；零新 enum／schema；正常核銷不產生財務 anomaly，真實超收仍保留。
- outbound: `external-integration/line/deposit-notifications` — 原 outer UoW 核銷 outbox payload 加入 LINE 通知標記；LINE 只讀事件及 typed DepositPayment，不消費 Orders 狀態，不反向建立財務或改寫 Orders。
- inbound: `scheduling/waiting-deposit-lock` — 無 settlement projection 的 Release 借用 typed 未收款確認；Apply fresh-read，來源版本與歷史變更受原 fingerprint 保護。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — 精確分配、超收處理及穩定錯誤。
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md` — owner delegation 與零部分帳務寫入。

## Verification
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_difference_resolution_mysql.py`
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_receipt_overage.py`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_receipt_partial_mysql.py`
- test_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_client_virtual_account_resolution.py`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/receipt-reconciliation/unit/`
- routing: `.arch-map/tests/domains/client-finance/subsystems/client-finance/index.md`
- presentation_test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/receipt_reconciliation.test.tsx` — composed case workspace consumer.
- 訂金通知跨 owner 驗證由 LINE `deposit-notifications` leaf 的 integration root 擁有。

## Provenance
- Owner 與金額核銷規則 — `architecture_declared` — Client Finance 正式規格。
- Workflow、repository 與既有測試位置 — `source_observed` — 上述 current implementation 與 test。

## Change triggers
核銷 eligibility、receipt identity、owner delegation、transaction owner 或驗證位置改變時重新核對。

- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/receipt-reconciliation/unit/test_first_payment_receipt_query.py` — first-stage receipt Query and same-transaction notification marker.

# Module: deposit-notifications

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
工會人員待辦主動建立訂金繳費提醒；讀取已提交且帶 LINE 通知標記的 Client Finance 核銷事件，
依 settlement identity 去重建立成功通知。客戶 LIFF 只讀本人案件繳費資料；協助按鈕沿既有客服
案件與聊天室留言流程。缺帳號／銀行代碼或客戶綁定時保留人員待辦。provider 前重驗來源與綁定。
不擁有財務、入帳或案件狀態，不通知群組、不補發歷史核銷。

## Implementation
- `subsystems/line/deposit_notifications.py`
- `infrastructure/mysql/deposit_notification_repository.py`
- `api/dependencies/line_deposit.py`
- `api/routes/line_deposit_payment.py`
- `line/static/deposit_payment.html`
- integration: `subsystems/line/delivery_worker.py`
- composition: `infrastructure/mysql/line_unit_of_work.py`
- composition: `api/dependencies/line_worker_operation.py`
- transport: `subsystems/line/matching_postback_application.py`
- customer service continuation: `infrastructure/mysql/customer_service_repository.py`
- typed UoW: `subsystems/line/ports.py`
- entry composition: `api/main.py`
- navigation: `line/static/gateway.html`
- staff presentation: `line/static/mobile_admin.html`

## Dependencies
- outbound: `client-finance/receipt-reconciliation` — typed DepositPayment Query 及帶 `line_deposit_notification` 標記的 committed Orders deposit event；不改 outbox status、不新增 enum。
- outbound: `customer-service` — 既有 create_or_append 及客服留言受理，不觸發群組告警。
- outbound: LINE Delivery — committed queue／lease／cancel／provider pipeline；不從 API 直接寄送。

- 原 followups / mobile Query 接受 optional case_no 作同案定位；與核銷狀態共同在分頁前篩選。無新查詢 owner 或資料狀態。
- 已核銷款項的原額沿 current obligation event，並與 settlement identity／正式入帳核對；待收餘額歸零仍可列通知，未結清提醒仍沿原餘額。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §6.7。
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md`。
- `CLIENT_DEPOSIT_BANK_CODE` 三碼銀行代碼；缺值不寄提醒。提醒 ready 同時核對既有 LIFF ID，兩端停用不可寄操作，提交仍沿原複核。`LINE_LIFF_ID` 沿用現有設定。

## Verification
- layout_status: `custom_current` — 使用 LINE Subsystem 既有 cross-owner integration root，涵蓋 Finance／LINE 邊界。
- integration_root: `tests/domains/external-integration/subsystems/line/integration/test_deposit_notifications.py`
- 共用寄送 runtime 與待辦 presentation 的回歸依原 Subsystem／mobile-assignment-review leaf 歸屬。

## Provenance
- owner、來源與公開入口 — `source_observed` — current implementation。
- 行為與效果上限 — `architecture_declared` — 規格 20 §6.7 及目前人工核准。

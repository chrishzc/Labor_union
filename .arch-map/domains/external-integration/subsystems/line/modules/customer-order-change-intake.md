# Module: customer-order-change-intake

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
讓 verified LIFF 客戶查詢自己的有效訂單、預覽結構化異動申請，並在明確確認後建立或延續 Customer Service 需求。此 Module 不修改 Client、Orders、Scheduling、Matching 或 Finance root，也不推定月嫂接受異動。

## Implementation
- `subsystems/line/customer_order_change_contracts.py`
- `subsystems/line/customer_order_change_application.py`
- `subsystems/customer_service/contracts.py` — 共用 ticket/event command；本 Module 只擴充 selected client/case context，不取得 Customer Service root ownership。
- `infrastructure/mysql/customer_order_change_repository.py` — Orders／Client owner facts 的 bounded read adapter。
- `infrastructure/mysql/customer_service_repository.py` — 既有 Customer Service ticket/event writer；只接受已驗證的 selected case context。
- `infrastructure/mysql/line_unit_of_work.py` — outer UoW composition。
- `api/dependencies/line_order_change.py`
- `api/schemas/line_order_change.py`
- `api/routes/line_order_change.py`
- `line/static/order_update.html`
- `line/static/gateway.html`
- `line/static/identity.html`
- `config/line_menu.json`
- `api/main.py` — bounded router composition only。

## Dependencies
- outbound: `external-integration/line/module:line-identity-management` — server-verified ID token、current customer binding 與 fresh binding evidence。
- outbound: `orders/orders/module:order-information` — selected customer order 的 typed read-only facts；不使用其管理端 presentation template。
- outbound: `clients/client-profile/module:profile-change` — current service-address owner value 與 profile version，只讀。
- outbound: `customer-service` — 在 caller-owned outer UoW 建立 durable ticket/event。

## Contracts
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md` — customer menu、申請型 LIFF 與人工確認邊界。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — verified LIFF、Preview／Apply、ticket 與 transaction 上位契約。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/customer-order-change-intake/`

## Safety boundary
Preview 零寫入；Apply fresh-lock current binding 與 selected Order，fingerprint 不符或 order stale 時 fail closed。成功只代表客服需求已提交並讀回，不代表正式訂單、服務地址、費用、排班或月嫂意願已改變。

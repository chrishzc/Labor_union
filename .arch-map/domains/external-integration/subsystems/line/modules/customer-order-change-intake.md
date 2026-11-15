# Module: customer-order-change-intake

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
讓 verified LIFF 客戶查詢自己的有效訂單、預覽結構化異動申請，並在明確確認後提交 Orders 異動申請。本入口只保存申請，正式訂單及相關業務根事實沿各 owning workflow 更新。

## Implementation
- `subsystems/line/customer_order_change_contracts.py`
- `subsystems/line/customer_order_change_application.py`
- `domains/orders/order_change_request.py` — 申請快照與狀態契約。
- `infrastructure/mysql/customer_order_change_repository.py` — Orders／Client owner facts 的 bounded read adapter。
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
- outbound: `orders/orders/module:order-change-requests` — 在同一 outer UoW 保存申請並讀回。

## Contracts
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md` — customer menu、申請型 LIFF 與人工確認邊界。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — verified LIFF、Preview／Apply、ticket 與 transaction 上位契約。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/customer-order-change-intake/`

## Safety boundary
Preview 零寫入。新提交 fresh-lock current binding 與 selected Order，fingerprint 不符或 order stale 時回傳 typed conflict。已提交同一請求讀回原申請。舊客服工單 `/apply` 回 410，新申請走 `/requests`。

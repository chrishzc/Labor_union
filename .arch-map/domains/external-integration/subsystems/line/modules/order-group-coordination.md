# Module: order-group-coordination

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以已驗證的 LINE 管理員身分綁定訂單群組、同步 Orders 提供的客戶與月嫂 audience，並以 durable LINE delivery intent 轉送群組邀請；不得以客戶／月嫂資料表中的投影取代 canonical LINE role binding。

## Implementation
- domain: `domains/line/order_group.py`
- application: `subsystems/line/order_group_application.py`
- contracts: `subsystems/line/order_group_contracts.py`
- audience adapter: `infrastructure/mysql/line_order_group_adapters.py`
- persistence adapter: `infrastructure/mysql/line_media_order_group_repository.py`

## Dependencies
- outbound: `orders` — 提供訂單狀態與指派對象。
- outbound: `client-finance` — 只讀正式訂金核銷 projection；未核銷或僅有未付款人工放行時禁止綁定群組與發送邀請。
- outbound: `line-identity-management` — 只接受 canonical bound role 與 owner projection 一致的收件人。
- outbound: `delivery-provider-transport` — 邀請訊息只經 committed delivery intent 投遞。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/domain/test_line_order_group_stage6.py`

## Provenance
- responsibility and implementation paths: `source_observed`

## Change triggers
Reconcile when群組綁定權限、訂單 audience、參與者同步、邀請 delivery 或 canonical identity boundary changes.

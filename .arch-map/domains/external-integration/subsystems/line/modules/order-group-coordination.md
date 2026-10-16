# Module: order-group-coordination

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以已驗證的 LINE 管理員身分綁定訂單群組、同步 Orders 提供的客戶與月嫂 audience，並以 durable LINE delivery intent 轉送群組邀請；不得以客戶／月嫂資料表中的投影取代 canonical LINE role binding。
管理端工作區僅觀察既有綁定，以 server 分頁／案件搜尋、目前客戶與指派月嫂、綁定後 membership 事件及可展開歷程呈現；不在網頁增加 mutation。

## Implementation
- domain: `domains/line/order_group.py`
- application: `subsystems/line/order_group_application.py`
- contracts: `subsystems/line/order_group_contracts.py`
- audience adapter: `infrastructure/mysql/line_order_group_adapters.py`
- persistence adapter: `infrastructure/mysql/line_media_order_group_repository.py`
- transport: `api/routes/line_order_groups.py`, `api/schemas/line_order_groups.py`
- presentation: `ui_react/src/components/LineOrderGroupWorkbench.tsx`, `ui_react/src/components/LineOrderGroupWorkbench.css`
- composition: `ui_react/src/pages/LineManagementPage.tsx` — order_groups branch only
- typed client: `ui_react/src/api/line_order_groups/`
- display adapter: `ui_react/src/adapters/line_order_groups/line_order_group_query_adapter.ts`

## Contracts
- 管理端成員與可唯一辨識的成員事件，沿同一 current Staff join 額外投影 nullable 公會編號；只格式化月嫂姓名，客戶、未辨識對象及群組／事件順序保持原契約。
- additive `/api/v1/line/order-groups/workspace/numbered`, `/workspace/{case_no}`, `/workspace/{case_no}/events/numbered`；舊 Query 不改義。
- Query 固定 0 commit／receipt／outbox／provider call，不輸出群組 ID、LINE user ID、actor ID、邀請網址或指紋。
- 成員為 Orders 目前客戶與指派月嫂；canonical role binding 與 owner projection 不一致時標未知。加入狀況只使用目前群組綁定版本之後的 membership 事件，不沿用舊群組的 joined 投影。

## Dependencies
- outbound: `orders` — 提供訂單狀態與指派對象。
- outbound: `client-finance` — 只讀正式訂金核銷 projection；未核銷或僅有未付款人工放行時禁止綁定群組與發送邀請。
- outbound: `line-identity-management` — 只接受 canonical bound role 與 owner projection 一致的收件人。
- outbound: `delivery-provider-transport` — 邀請訊息只經 committed delivery intent 投遞。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/order-group-coordination/`
- existing policy oracle: `tests/domains/external-integration/subsystems/line/domain/test_line_order_group_stage6.py`
- ui integration: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_order_group_workbench.test.tsx`

## Provenance
- responsibility and implementation paths: `source_observed`

## Change triggers
Reconcile when群組綁定權限、訂單 audience、參與者同步、邀請 delivery 或 canonical identity boundary changes.

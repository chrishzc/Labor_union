# Module: order-group-coordination

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以已驗證的 LINE 管理員身分綁定訂單群組、同步 Orders 提供的客戶與月嫂 audience，並以 durable LINE delivery intent 轉送群組邀請；不得以客戶／月嫂資料表中的投影取代 canonical LINE role binding。
管理端「案件群組」以 server 分頁／案件搜尋、目前客戶與指派月嫂、綁定後 membership 事件及可展開歷程呈現。具群組綁定權限者可手動解除現有綁定，再永久刪除已解除案件的群組歷程。群組解散不觸發刪除。
工會 LINE 工作台另以正式已核銷的未結案案件與現有群組綁定差集呈現「尚未建群」，server 分頁、
零寫入，僅提供案號、已核銷金額及複製綁定指令；不要求客戶簽約或推進案件。
工會 LINE 工作台「訂金已付尚未建群」另提供「開工問候未送出紀錄」，以唯讀分頁呈現無有效案件群組的略過紀錄，獨立於訂金待辦與件數。

操作人員的 18 項群組設定完成、邀請排入、資格／設定與格式錯誤均使用既有純函式的固定中文；新提示只建立原群組、原事件的 Reply-only 工作，不讀通知文案設定，缺少或失敗 Reply 不補 Push。客戶／月嫂私人邀請卡仍沿原發送與可編輯文案契約，歷史設定不刪改。

## Implementation
- domain: `domains/line/order_group.py`
- application: `subsystems/line/order_group_application.py`
- group_helper: `subsystems/line/group_helper_application.py` — 案件群組月嫂小幫手選單、確認開工日、雙方合意延期、服務排程、專員協助與常見問答。正式完工後，本案月嫂可點選滿意度調查問卷，群組互動走 Reply。
- contracts: `subsystems/line/order_group_contracts.py`
- audience adapter: `infrastructure/mysql/line_order_group_adapters.py`
- persistence adapter: `infrastructure/mysql/line_media_order_group_repository.py`
- transport: `api/routes/line_order_groups.py`, `api/schemas/line_order_groups.py`
- staff todo transport: `api/routes/line_mobile_admin.py` — `/order-group-todos`，verified Admin／ORDER_GROUP_READ；`view=opening_greeting_skips` 查閱略過紀錄。
- staff todo presentation: `line/static/mobile_admin.html` — 尚未建群分組、開工問候略過紀錄，複製指令無外部效果。
- presentation: `ui_react/src/components/LineOrderGroupWorkbench.tsx`, `ui_react/src/components/LineOrderGroupWorkbench.css`
- composition: `ui_react/src/pages/LineManagementPage.tsx` — order_groups branch only
- typed client: `ui_react/src/api/line_order_groups/`
- display adapter: `ui_react/src/adapters/line_order_groups/line_order_group_query_adapter.ts`

## Contracts
- `綁定群組` 用 Reply 引導同一操作人員依序輸入案號與邀請網址。前兩步由原群組、原事件的 Reply 工作記錄進度。有效網址通過資格重查後，綁定、網址與私人邀請工作一併提交。見 [群組指令與驗收](../../../../../requirements/17A_LINE_Gateway_Inbox與通知投遞正式規格.md#3-服務群組綁定待辦與代班邀請)。
- 單行群組設定指令為 `綁定訂單 案件編號 邀請網址`，空白／全形空白／換行分隔；格式錯誤回覆原因與範例，零設定寫入。私有網址與綁定同交易保存，更新網址不清成員歷史。
- `發送邀請` 讀取保存網址並重新驗證付清／身分資格，經 committed delivery 投遞；provider 前核對群組版本、網址及 audience，失效工作取消。
- nullable `invitation_url` 由 `db/schema_parts/1053_line_order_group_invitation_url.sql` additive 保存；舊綁定不回填網址，管理 Query 不暴露。
- 管理端成員與可唯一辨識的成員事件，沿同一 current Staff join 額外投影 nullable 公會編號；只格式化月嫂姓名，客戶、未辨識對象及群組／事件順序保持原契約。
- additive `/api/v1/line/order-groups/workspace/numbered`, `/workspace/{case_no}`, `/workspace/{case_no}/events/numbered`；舊 Query 不改義。
- Query 固定 0 commit／receipt／outbox／provider call，不輸出群組 ID、LINE user ID、actor ID、邀請網址或指紋。
- `POST /workspace/{case_no}/unbind` 與 `/delete-history` 使用 `ORDER_GROUP_BIND`、目前綁定版本及單一交易。解除清除現行群組與邀請網址並記錄解除歷程。刪除僅清除未綁定案件的群組事件及舊成員投影，保留版本列和刪除收據。
- `paid_uncreated_todos` 只讀 canonical settled projection 且訂金金額大於零、正常未結案 Orders 及尚無 group_id；不將銀行待核銷或客戶自述視為已付。
- `opening_greeting_skips` 只讀 `service_start_greeting_no_group` 稽核事件，投影案號和紀錄時間，不讀其他稽核種類或投遞記錄。
- 成員為 Orders 目前客戶與指派月嫂；canonical role binding 與 owner projection 不一致時標未知。加入狀況只使用目前群組綁定版本之後的 membership 事件，不沿用舊群組的 joined 投影。
- 問卷按鈕與 Postback 都驗證目前案件群組、正式完工、有效服務排班與月嫂身分綁定。點選後發送「通知與發送」的可編文字範本，預設文案不含網址。

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
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_group_helper_application.py`

## Provenance
- responsibility and implementation paths: `source_observed`

## Change triggers
Reconcile when群組綁定權限、訂單 audience、參與者同步、邀請 delivery 或 canonical identity boundary changes.

# Module: order-information

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
提供既有案件訂單資訊的 typed Query 與管理端 readback；不改寫 Orders root facts。
Case Import 照護與獎金協調 named projection 疊加 current BeClass correction state，保留原始問卷；不從三節文字推導薪資或客戶應付。
初步候選資訊由 candidate-specific 投影重用相同命名欄位；無正式 assignment 時不虛構指派，未知費用待確認，預覽全文與收件對象綁定後交 Scheduling durable sender。一般候選預覽的服務起訖日讀取 current Orders planned period，不沿用初次加入候選池時的 contact snapshot；明確傳入的重聯絡期間仍由 caller 擁有，正式 plan／assignment 沿用各自 owner 期間。資訊一的每日時段、每日時數與是否下廚讀取 current Orders Terms，讓客戶同意調整後的重新詢問不沿用舊表單文字。
欄位缺值或來源未決以 warnings 呈現且不阻擋目前資料投影；模板結構等技術錯誤才列為 blockers。

依 2026-10-30 最新人工裁決，初步候選月嫂收到的資訊一只顯示月嫂薪資單價、預估總薪資與預計付款日；使用 Payroll 政策及目前 Orders 約定服務量的唯讀預估，不虛構 assignment／服務日、不建立正式應付，來源缺失標示待確認。月嫂版不帶客戶訂金、分期、客戶應付或其繳款日。客戶正式推薦版繼續借用 current 客戶契約 typed projection，包含訂金、分期、樓層費及繳款日，不帶月嫂薪資；兩種財務內容不共用。
客戶付款查詢使用 current Orders confirmed／預計日期與 Finance stage plan；沒有執行指派時不採舊 commitment 的服務量，也不因舊媒合方案失效而清空付款欄位。正式契約與正式 plan／assignment 的來源及過期驗證保持各自 owner 契約。
服務方式「無休」及未選休假星期沿用客戶契約投影的「連續服務」，讓資訊一畫面、寄送前預覽與付款金額一致。

## Implementation
- `subsystems/orders/order_information.py` — 共用 case-only 服務／照護內容與 saved-date 週說明 typed projection；逐人 Preview 保留 recipient-bound fingerprint，不建立假 assignment 或 candidate。
- `subsystems/orders/order_information.py`
- `infrastructure/mysql/order_information_repository.py`
- `db/templates/tpl_info_01.json`
- `db/templates/tpl_info_02.json`
- `api/routes/orders.py`
- `api/dependencies/order_information.py`
- `api/schemas/order_information.py`
- `api/schemas/order_detail.py`
- `subsystems/orders/detail_query.py`
- `ui_react/src/api/orders/order_information_client.ts`
- `ui_react/src/components/OrderInformationSheets.tsx`
- `ui_react/src/pages/OrderWorkbenchV2Page.tsx`
- `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Verification
- Python test root: `tests/domains/orders/subsystems/orders/modules/order-information/`
- React client: `ui_react/src/tests/orders_query_client.test.ts`
- React page: `ui_react/src/tests/order_workbench_v2_page.test.tsx`

## Provenance
- Current route, application, MySQL adapter and React callers observed in source.

# Module: order-card-projection

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將既有 Orders card typed projection轉為管理端可讀的案件根事實與正式指派摘要，並保護同一current Orders page既有workflow surface的業務／技術資訊分層；媒合查詢沿用既有 Scheduling typed client，讓管理員調整四項 server-backed 條件後重新取得候選。取消影響的一般畫面只呈現日期、正式服務量、客戶帳務與服務人員薪資調整；條款、服務日期與實際開工表單使用變更前後及稽核必填等業務語言。技術識別、raw action/direction、raw field name及owner/version只保留在按需技術詳情。不得改寫Orders lifecycle、cancellation rule或Scheduling／Finance／Payroll root facts。

## Implementation
- primary:
  - `subsystems/orders/summary_query.py`
  - `infrastructure/mysql/order_summary_query_repository.py`
  - `api/schemas/order_summary.py`
  - `ui_react/src/adapters/orders/order_summary_adapter.ts`
  - `ui_react/src/adapters/orders/order_card_projection_adapter.ts`
  - `ui_react/src/pages/OrderWorkbenchV2Page.tsx`
  - `ui_react/src/components/OrdersIntakeRepairCard.tsx`
  - `ui_react/src/components/OrderIntakeRepairPanel.tsx` — 案件進件資料區分原始 HCM 欄位待修正與尚未補齊的案件資料；服務開始日／天數僅顯示實際 missing fields，草稿以 owner Preview 保存值為準，不被一般明細空值覆蓋；完整資料的早期修改由人員主動展開；保留既有 Preview／Apply 與回讀流程。
  - `ui_react/src/api/orders/order_intake_completion_client.ts` — typed intake Preview／Apply 與 current service-time 解碼；缺時數案件沿用同一補件命令保存時間，回讀必須比對日期、天數及時段／時數。
  - `OrderIntakeRepairPanel` 在案件處理提供唯讀缺件摘要，在名冊組合正式補件；名冊補件收到收據且回讀一致後，以 fresh completion Preview 判定能否續行既有 completion Apply，不在 UI 推導 lifecycle。結果未明維持原冪等操作，已收到收據則僅回讀，回讀完成前保持離開限制。
  - `ui_react/src/components/OrderTerminalAggregateLane.tsx` — 呈現既有typed結案彙總，不重算結案規則。
  - `ui_react/src/pages/OrdersPage.css`
  - `subsystems/orders/card_projection_query.py`
  - `infrastructure/mysql/orders_card_projection_repository.py`

## Dependencies
- inbound: Orders React route — 只讀取既有typed projection。
- outbound: `scheduling/scheduling` — 正式指派資料只顯示typed owner projection，不由React重算。
- outbound: `case-import/hcm-current-workbook-import` — 透過既有 typed current review Query 顯示本案原始進件欄位問題，不重新判定問題解除或異動匯入 roots。
- outbound: `clients/client-profile/profile-change` — 案件處理組合 Client Profile 欄位修正面板，提供電話及服務方式等 current review 欄位的直接修正，保存後重讀 review；姓名補件以名冊 typed Client Profile facts 核對正式回讀，缺日期／天數不借用完整 Orders projection。Orders 補件命令保持既有 writer。

## Contracts
- 案件摘要保留純姓名 `staff_name`，另投影 `staff_display_label` 為 current Staff 公會編號及姓名；沿既有正式指派優先、歷史配對備援與分段順序，不以姓名查找人員；標籤改變參與 ETag。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders root facts。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 管理端資訊層級與技術詳情邊界。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/order_workbench_v2_page.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_terminal_aggregate.test.tsx`
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-card-projection/`
- test_root: `ui_react/src/tests/fixtures/orders_real_data_fixtures.ts`
- test_root: `ui_react/src/tests/orders_no_fake_mutation.test.ts`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/order-card-projection.md`

## Provenance
- Orders／Scheduling owner boundary — `architecture_declared` — current formal specs。
- React source與既有focused regression — `source_observed` — current repository。

- Intake panel／card 的一般補件備註可選填，不再因原因留白停用儲存；實際缺件、Preview blocker 與忙碌狀態仍限制操作。

## Change triggers
Reconcile when card projection contract、Orders cancellation presentation、營運摘要欄位、technical-details boundary、React entry或focused test location changes。

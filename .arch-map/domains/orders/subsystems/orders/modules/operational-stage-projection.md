# Module: operational-stage-projection

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將 Case Import 或 Case Architecture Bootstrap 的正式進件 lineage，連同 Orders、Scheduling、Client Finance 與 Payroll 的唯讀根事實整合為營運階段投影；單一 owner fact 不可用時只局部標示 unavailable，不使整頁訂單清單失效。目前有效 Scheduling generation 由歷史精算重啟或其服務日期接手 command 建立，且歷史綁定人員唯一時，候選、詢問、意願與推薦由該 current provenance 判定完成；舊重啟事件不得在取消、重開或後續 replacement generation 繼續冒充現況。指定 workbench scope 時先依 canonical lifecycle 排除 scope 外案件，再投影十三核心階段；scope 內資料仍採 fail-closed。既有七階段／十一 SOP 契約保持相容，待辦看板 Beta 另由同一正式根事實轉成十三核心階段唯讀契約。

## Implementation
- presentation: 「尋找月嫂與詢問意願」提供候選月嫂／多月嫂分段切換，沿用 `OrderMultiCaregiverPlanPanel` 的 2–4 段查詢與正式 writer；只在明確採用組合、收據與分段回讀成功後接續客戶確認準備。已開啟的清單與分段表單保留掛載；建立結果未明時保留原操作恢復入口並禁止切換。
- presentation: 推薦確認沿用前段接案同意，只有意願通知變更才人工記錄；客戶三份資訊共用唯讀 dialog，主頁確認寄送／手動客戶決策。換人選擇接任者及服務段落，只填原因，依 fresh 指派 Query 分流，保留原操作與 immutable create receipt；不以畫面切換推進階段。
- projection: 現行推薦的最新正式意願事件為不承接時，推薦確認改為 blocked 並回到換人待辦，包含已有 current generation 正式指派的案件；既有客戶接受或 waiting lock 不掩蓋此通知。讀取最新事件、不改寫 Orders lifecycle 或既有指派；實際換人／代班沿既有分流。
- presentation: 進件工作區統一顯示缺件清單與前往名冊補件的深連結，移除重複服務條件表單；上方入口改為編輯客戶與訂單資料。名冊返回 `#order-workbench-v2?case=…` 時，以 bounded typed lifecycle-all Query 唯一比對相同案件，重新開啟其正式目前待辦；關閉後清除案件深連結。既有取消／重開及服務安排功能保持原 owner 流程。
- 進件條款缺漏提示直接列出 Orders current facts 缺少的開始日、天數、服務時間或樓層加給；待辦看板與案件處理不再以技術描述或階段標題取代欄位名稱。既有階段／完整性判定不變。
- presentation: 待辦看板以卡片進入單一案件工作畫面；五個工作群組各自依正式資料顯示狀態，進件區呈現唯讀缺件清單並導向名冊補件，共用案件摘要位於上方，十三階段只作紀錄與導覽，不構成線性操作前置。不再提供案件資料／案件異動分頁；取消／受控重開位於右上角，沿用既有操作面板與正式回讀，在 dialog 中保留結果未明時的離開限制及完成收據。日期更正與既有換人入口位於服務安排，唯讀聯絡、帳務及 LINE 紀錄由上方摘要列入口展開，同列最右側提供本案客戶與訂單資料編輯入口；下方不重複顯示資料摘要與通用明細讀取失敗提示，必要補件與 Terms 缺漏提示仍保留。群組切換不推進後端階段，已開啟表單保留掛載。不在工會操作頁顯示技術來源。正式 Orders 明細缺件時不得持續顯示 loading；歷史分支可並列呈現 immutable adoption evidence 的來源期間，但不冒充正式約定或實際日期。元件沿用原 `OrderWorkbenchV2Drawer` symbol，但不再使用 Drawer overlay；導覽為現有 route 內的本機狀態。
- presentation: 移除獨立收款結算工作群組及重複訂金放行，Finance current stage 導向服務安排；已服務完成案件第五項顯示完工摘要、實際期間、Orders 完工事件時間與兩端結算狀態。單一同案帳務入口帶 case_no/from=workbench，Finance 承接歷史帳務完成及返回同案；未更動十三階段與 lifecycle owner。
- presentation: 待辦看板固定查詢 `in_progress`，案件受理統計預設收合；完整階段與件數按鈕常駐展開，作為唯一作業階段篩選入口，不再顯示重複下拉選單。統計提供年度／季度／月份與固定四項資格、六項狀態欄位，透過 Reporting typed GET 讀取正式統計；loading／failure 顯示缺值並可手動重試，取消舊請求以避免 stale 數字。統計期間不改變下方待辦 query；看板重新整理與案件處理後重新讀取統計。工作區預設隨正式回讀接續目前待辦及服務子作業，手動查阅其他事項時保留位置並提供返回目前待辦；已開啟面板保留掛載供回讀完成。進件基本資料齊備不代表服務條件齊備，進件缺件或補件資格讀取失敗必須在進件工作區顯示原因；完整 Terms 操作移至名冊。
- primary:
  - `subsystems/orders/stage_projection_query.py`
  - `subsystems/orders/core_stage_projection_query.py`
  - `subsystems/orders/core_stage_filter_query.py`
  - `subsystems/orders/government_subsidy_projection_query.py`
  - `ui_react/src/api/orders/load_all_core_stage_timelines.ts`
  - `ui_react/src/api/orders/order_core_stage_projection_client.ts`
  - `ui_react/src/api/orders/order_government_subsidy_projection_client.ts`
  - `ui_react/src/adapters/orders/order_core_stage_projection_adapter.ts`
  - `ui_react/src/pages/OrderWorkbenchV2Page.tsx`
  - `ui_react/src/components/WorkbenchCaseStatistics.tsx`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`
  - `ui_react/src/components/OrderWorkbenchV2OwnerContext.tsx`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.css`
  - `ui_react/src/pages/OrderWorkbenchV2Page.css`
  - `ui_react/src/components/OrderCandidateQueryPanel.tsx`
  - `ui_react/src/components/OrderMultiCaregiverPlanPanel.tsx`
  - `ui_react/src/components/OrderFormalRecommendationPanel.tsx`
  - `ui_react/src/components/OrderRecommendationReplacementPanel.tsx`
  - `infrastructure/mysql/orders_stage_projection_repository.py`
  - `infrastructure/mysql/order_government_subsidy_projection_repository.py`
- entrypoints:
  - `api/routes/orders_stage_projection.py`
  - `api/routes/orders_core_stage_projection.py`
  - `api/dependencies/orders_stage_projection.py`
  - `api/schemas/order_government_subsidy_projection.py`

## Dependencies
- outbound: `global/reporting/weekly-operations-report` — 讀取固定十欄、年度總數與曆年期間的案件受理統計；不在 Orders presentation 重算正式分類。
- outbound: `scheduling/scheduling` — 讀取有效等待訂金鎖、正式服務期間與 service-time terms；有效鎖是推薦確認已跨入契約準備的直接投影證據。
- outbound: `client-finance/client-finance` — 讀取定金與客戶 obligation projection。
- outbound: `payroll/payroll` — 讀取月嫂薪資 obligation projection。
- outbound: `case-import | case-architecture-bootstrap` — 任一正式建立事件皆可提供進件 lineage；不得要求 bootstrap 案件補造 Case Import 收據。
- outbound: `case-import/hcm-current-workbook-import` — 待補件卡片讀取既有 current HCM review 的欄位清單，顯示原始進件待修正原因；不以服務條件缺漏取代欄位驗證問題，不改變正式階段或 lifecycle。

## Contracts
- `api/routes/orders_stage_projection.py` — `/api/orders/operational-timelines` typed read-only contract。
- `api/routes/orders_core_stage_projection.py` — `/api/orders/core-stage-timelines` Beta typed read-only contract；十三核心階段中的 11～13 直接沿用 service completion、client settlement、staff payout owner 子投影。

## Provenance
- Query composition and API entry — `source_observed` — `subsystems/orders/stage_projection_query.py`, `subsystems/orders/core_stage_projection_query.py`, `api/routes/orders_stage_projection.py`, and `api/routes/orders_core_stage_projection.py`.

## Change triggers
Reconcile when stage identity, availability semantics, owner facts, API route, or projection test root changes.

## Verification
layout_status: custom_current
UI verification follows the same Orders owner hierarchy inside the Vitest source root; Python verification remains in the repository test root.
- test_root: `tests/domains/orders/subsystems/orders/modules/operational-stage-projection/`
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/operational-stage-projection/`
- test_root: `ui_react/src/tests/order_workbench_v2_candidate_pool_refresh.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_mutation_refresh.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_terms_mutation.test.tsx`
- test_root: `ui_react/src/tests/order_workbench_v2_owner_context.test.tsx`

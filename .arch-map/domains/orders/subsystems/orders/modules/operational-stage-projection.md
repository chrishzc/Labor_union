# Module: operational-stage-projection

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將 Case Import 或 Case Architecture Bootstrap 的正式進件 lineage，連同 Orders、Scheduling、Client Finance 與 Payroll 的唯讀根事實整合為營運階段投影；單一 owner fact 不可用時只局部標示 unavailable，不使整頁訂單清單失效。目前有效 Scheduling generation 由歷史精算重啟或其服務日期接手 command 建立，且歷史綁定人員唯一時，候選、詢問、意願與推薦由該 current provenance 判定完成；舊重啟事件不得在取消、重開或後續 replacement generation 繼續冒充現況。指定 workbench scope 時先依 canonical lifecycle 排除 scope 外案件，再投影十三核心階段；scope 內資料仍採 fail-closed。既有七階段／十一 SOP 契約保持相容，待辦看板 Beta 另由同一正式根事實轉成十三核心階段唯讀契約。

## Implementation
- presentation: 待辦看板以卡片進入獨立案件工作畫面；六個工作群組各自依正式資料顯示狀態，十三階段只作紀錄與導覽，不構成線性操作前置。群組切換不推進後端階段，已開啟表單保留掛載。案件資料與案件異動分開呈現，不在工會操作頁顯示技術來源。正式 Orders 明細缺件時不得持續顯示 loading；歷史分支可並列呈現 immutable adoption evidence 的來源期間，但不冒充正式約定或實際日期。元件沿用原 `OrderWorkbenchV2Drawer` symbol，但不再使用 Drawer overlay；導覽為現有 route 內的本機狀態。
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
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.css`
  - `ui_react/src/pages/OrderWorkbenchV2Page.css`
  - `ui_react/src/components/OrderCandidateQueryPanel.tsx`
  - `ui_react/src/components/OrderMultiCaregiverPlanPanel.tsx`
  - `infrastructure/mysql/orders_stage_projection_repository.py`
  - `infrastructure/mysql/order_government_subsidy_projection_repository.py`
- entrypoints:
  - `api/routes/orders_stage_projection.py`
  - `api/routes/orders_core_stage_projection.py`
  - `api/dependencies/orders_stage_projection.py`
  - `api/schemas/order_government_subsidy_projection.py`

## Dependencies
- outbound: `scheduling/scheduling` — 讀取有效等待訂金鎖、正式服務期間與 service-time terms；有效鎖是推薦確認已跨入契約準備的直接投影證據。
- outbound: `client-finance/client-finance` — 讀取定金與客戶 obligation projection。
- outbound: `payroll/payroll` — 讀取月嫂薪資 obligation projection。
- outbound: `case-import | case-architecture-bootstrap` — 任一正式建立事件皆可提供進件 lineage；不得要求 bootstrap 案件補造 Case Import 收據。

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

# Module: matching-coordination

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
維護 Scheduling-owned matching coordination 的 candidate/decision/plan/package lineage 與 typed Query／Preview／Apply contract，向 API 暴露可驗證的 current coordination state；React workbench 目前僅保留 isolated-tested、尚未接入 App route 的 transport/presentation。

## Implementation
- `api/routes/candidate_contact_pool.py`
- `api/schemas/candidate_contact_pool.py`
- primary:
  - `domains/scheduling/matching_coordination.py`
  - `domains/scheduling/candidate_contact_response.py` — 候選確認資訊、條件調整、沒有意願與受影響 criteria 的 typed 規則。
  - `subsystems/scheduling/matching_coordination_contracts.py`
  - `subsystems/scheduling/matching_notification_contracts.py` — formal matching contact、customer confirmation preview 與 durable notification typed contracts。
  - `subsystems/scheduling/matching_plan_workflow.py`
  - `subsystems/scheduling/segmented_availability_query.py`
  - `subsystems/scheduling/candidate_contact_pool_workflow.py` — 初步候選加入及聯絡重新檢查預計期間 availability；客戶同意日期調整後的重新聯絡會以 current Orders 日期重驗完整 coverage，在同一交易更新 contact period／fingerprint、留存前後日期事件並排入新卡，但不建立正式服務日期。
  - `subsystems/scheduling/matching_line_cards.py` — 候選資訊與正式媒合的 pure Flex renderer。
  - `subsystems/scheduling/proposed_weekly_service_projection.py` — proposed formal plan 以 Monday–Sunday 與實際 work dates 語意產生每周服務中投影；不讀 effective schedule。
  - `subsystems/scheduling/customer_confirmation_download.py` — 由 confirmation package 簽發、到期即失效且檔案範圍受限的客戶履歷下載 reference。
  - `subsystems/line/candidate_contact_postback_application.py` — 將候選資訊卡片回覆轉交給 recipient-bound owner adapter。
  - `subsystems/line/candidate_contact_response_application.py` — 驗證 candidate/customer LIFF recipient，追加結構化回應並建立直接協調 delivery task。
  - `subsystems/line/candidate_contact_coordination_worker.py` — 以 provider sent time 處理 24 小時逾期、willing short-circuit、全池完成後的調整彙整，以及「非空已聯繫池全員終結、零調整條件或客戶已回覆可以／無法調整」的工會人工跟進衍生查詢與一次性群組通知；另投影 exact accepted adjustment、受影響候選與 post-answer Orders Terms receipt gate，供工會完成正式修改後再重新詢問月嫂。
  - `subsystems/scheduling/historical_pending_deposit_matching.py` — Historical Adoption 可用的 typed proposed-plan writer port。
  - `domains/scheduling/holiday_work_agreement.py` — current plan/version/date-bound 的客戶與全體月嫂國定假日上班協調規則。
  - `subsystems/scheduling/holiday_work_agreement_workflow.py` — 協調結果 Preview／Apply，fresh-read 現行 proposed plan、全分段與官方國定假日後才可寫入。
- `subsystems/scheduling/matching_coordination_workflow.py`
- `subsystems/scheduling/matching_notification_application.py` (zero-pool client decision response owner)
  - `subsystems/scheduling/matching_coordination_application.py` — P3 typed leave/date handoffs
  - `infrastructure/mysql/matching_coordination_repository.py`
  - `infrastructure/mysql/matching_coordination_facts_adapter.py`
  - `infrastructure/mysql/historical_pending_deposit_matching_repository.py` — 借用 caller transaction 寫入可由 active Matching Query 讀取的正式 plan／segment roots。
  - `infrastructure/mysql/segmented_availability_repository.py`
  - `infrastructure/mysql/candidate_contact_pool_line_reply_repository.py` — 以已送出資訊事件和 staff LINE identity 重新驗證回覆後，追加意願事件；原 24 小時內本人可用新事件更正自己的意願，current projection 採每位候選最新回覆，其他候選已願意時仍拒絕。
  - `infrastructure/mysql/matching_holiday_work_agreement_repository.py` — immutable current-plan agreement evidence 與 accepted-date readback。
  - `infrastructure/mysql/matching_notification_repository.py` — current Stage 5 confirmation package 的 plan/履歷/order-information/proposed-weekly preflight projection。
- entrypoints:
  - `api/routes/caregiver_segment_availability.py` — 候選詢問 `/candidate-contact-pool/availability/search` 與正式分段查詢分離；詢問只接受單人查詢。
  - `api/routes/line_candidate_contact.py`、`api/schemas/line_candidate_contact.py` — recipient-bound candidate/customer query/submit contract 與 LIFF page。
  - `api/routes/line_mobile_admin.py`、`line/static/mobile_admin.html` — 工會媒合人工跟進清單、通知狀態及正式排班工具入口；`system_admin` 綁定者可在同一 LIFF 先經 Orders Terms Query／Preview／Apply，再以 server-verified receipt gate 預覽及重送受影響原候選，初次搜尋零候選不列為通知待辦。
  - `line/static/candidate_contact.html`、`line/static/candidate_contact_customer.html` — 月嫂結構化回應與客戶直接協調介面；LINE identity 只來自 verified ID token。
  - `ui_react/src/api/scheduling/matching_candidate_workflow_client.ts`、`ui_react/src/components/OrderCandidateQueryPanel.tsx` — 待辦工作台初步候選查詢走預計期間入口；多月嫂正式查詢仍走原入口。
  - `api/routes/matching_coordination.py`
  - `api/schemas/matching_coordination.py`
  - `ui_react/src/api/matching_coordination/matching_coordination_client.ts` — isolated-tested transport client; no current App route consumer.
  - `ui_react/src/components/MatchingCoordinationWorkbench.tsx` — isolated-tested workbench; no current App route consumer.
  - `api/routes/matches.py`、`api/schemas/matches.py` — `/holiday-work-agreements/preview`、Stage 5 customer confirmation 與到期履歷 download contract。
  - `ui_react/src/api/scheduling/matching_plan_communication_client.ts`、`ui_react/src/components/HolidayWorkAgreementActions.tsx`、`ui_react/src/components/OrderFormalRecommendationPanel.tsx` — current Order Workbench V2 的人工協調 UI；不宣稱為 LINE delivery/reply。
  - `db/schema_parts/1032_matching_holiday_work_agreements.sql` — additive immutable agreement and participant records.
  - `scripts/run_holiday_work_agreement_scenario.py` — disposable `lu_test_*` scenario runner；透過 typed public API 驗證任意假日排班拒絕、雙方同意後納入服務日，以及後續拒絕立即撤銷。

## Dependencies
- outbound: `orders/order-information` — 候選資訊使用命名投影；預覽與寄送共用相同內容，不建立虛構 assignment。
- outbound: `orders/orders` — case/lifecycle boundary.
- outbound: `orders/historical-precision-restart` — restarted `訂單成立` 案件可進入正常媒合；已失效且沒有 generation ownership 的歷史 assignment 不再占用候選檔期。
- inbound: API transport invokes typed coordination commands, not direct DB writes. The React client/workbench remain isolated-tested without a current App route consumer；candidate LIFF 與 recipient-bound postback 則為 current live LINE inbound，經 application／adapter 追加 candidate-contact events。
- inbound: `orders/historical-adoption` — 只有 discussion、開始日空白且月嫂唯一可辨識的來源列，才在同一 outer UoW 建立 proposed plan。
- P3 handoff: committed M3 intents carry immutable `LU96-M3-*` source identity and recipient selector; P5 owns delivery task/provider consumption.

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling ownership.
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — matching preference/unavailability facts.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/`
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/`
- test_root: `ui_react/src/tests/candidate_contact_pool_client.test.ts`
- test_root: `ui_react/src/tests/order_workbench_v2_candidate_query.test.tsx` — 既有詢問查詢元件與完整候選回讀測試。
- test_root: `ui_react/src/tests/order_workbench_v2_candidate_contact_status.test.tsx` — 既有意願確認／回讀元件測試。
- higher_boundary:
  - tests/integration/ (shared legacy higher-boundary root)
- layout_gap:
  - `tests/test_matching_coordination_repository.py` — still uses a repo-relative schema path and remains at its observed path until that path dependency is reconciled.
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Domain ownership — `architecture_declared` — Scheduling specs.
- Source/API/UI paths — `source_observed` — current repository search.
- Module-owned contract/domain/workflow/facts/API-route tests — `source_observed` — architecture-aligned test root.
- Historical pending-deposit typed port、borrowed-connection adapter 與 owner-local tests — `source_observed` — current source and canonical module test root.
- Segmented availability query/repository 的 lifecycle gate 與 assignment occupancy filtering — `source_observed` — current Scheduling query and MySQL facts adapter.
- Scheduling React entry contract — `source_observed` — same architecture-aligned module test root.
- Holiday-work scenario runner — `source_observed` — public API scenario uses the matching coordination agreement route and service-date readback.
- Candidate direct-coordination LIFF、24-hour worker、工會人工跟進 LIFF／群組通知、recipient-bound reply adapter 與 canonical module tests — `source_observed` — current source and architecture-aligned test root.
- Repository test exception — `source_observed` — current flat path with relocation-sensitive schema lookup.

## Change triggers
Reconcile when coordination owner, case lifecycle eligibility, assignment occupancy semantics, package/event contract, presentation hierarchy, API route/schema, persistence adapter or focused test root moves.

# Module: matching-coordination

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
維護 Scheduling-owned matching coordination 的 candidate/decision/plan/package lineage 與 typed Query／Preview／Apply contract，向 API 暴露可驗證的 current coordination state；React workbench 目前僅保留 isolated-tested、尚未接入 App route 的 transport/presentation。

## Implementation
- manual commute: `subsystems/scheduling/commute_query.py` — 單次人工觸發、Google 計費月、metadata-only 用量與人工全帳戶核對；既有 `background_jobs` 承接 committed inline claim，零新 schema、零自動 provider retry。
- adapters: `infrastructure/http/google_routes.py`、`infrastructure/mysql/commute_query_repository.py` — 固定官方 TWO_WHEELER／TRAFFIC_AWARE_OPTIMAL transport（查詢當下路況）、Staff/Client 地址唯讀來源、用量 metadata；不保存地址或 Google 距離。
- entrypoint: `api/routes/commute.py` — admin-only single caregiver POST、usage GET、manual billing reconciliation POST、case-scoped `GET /orders/{case_no}/commute-history`（最新 50 筆 metadata-only 紀錄）；由 `api/main.py` 組裝。
- presentation: `ui_react/src/api/scheduling/commute_client.ts`、`ui_react/src/components/CaregiverCommute.tsx`、`ui_react/src/components/CaregiverCommute.css` — 既有新增候選／候選卡片／分段已選月嫂內的逐位按鈕，通勤時間與距離直接在指定月嫂卡片呈現；同一分頁以案件＋月嫂共用結果與 pending 狀態，關閉／切換案件不重查，重新整理或登入狀態變更清除。共享用量只在新增候選抽屜顯示，不掛載 50 筆歷史清單，無整批／自動查詢。
- `api/routes/candidate_contact_pool.py`
- `api/schemas/candidate_contact_pool.py`
- primary:
  - `ui_react/src/components/CandidateInquiryDialog.tsx` — 候選新增與共用資訊的 native modal；保留焦點與操作期間保護。接案意願改在月嫂卡片內展開填寫。
  - `ui_react/src/components/OrderCandidateInformationPanel.tsx` — case-only 共用文件，不要求候選；三份各自選收件人、逐人 recipient-bound Preview／Apply 與 exact receipt 回讀。每週只寄送已保存的 Orders 日期。
  - `ui_react/src/components/CandidatePlannedServiceDates.tsx` — 既有 Orders 日期 writer 的共用／個別週說明入口，試算零寫入，未保存不可寄送。
  - `db/schema_parts/232_candidate_weekly_information.sql` — fresh supplemental `info_3_sent` 事件，不重新啟動資訊-1／2 的意願期限與全池完成 gate。
  - `db/schema_parts/1051_candidate_weekly_information.sql` — byte-equivalent preserve-only enum widening；保留歷史事件與 ordinal。
  - `domains/scheduling/matching_coordination.py`
  - `domains/scheduling/staff_matching_preferences.py` — 區域／週間服務的純提示比對，回傳 matched／not_matched／pending 與月嫂原登錄值；不讀或同步數字偏好副本。
  - `domains/scheduling/candidate_contact_response.py` — 候選確認資訊、條件調整、沒有意願與受影響 criteria 的 typed 規則。
  - `subsystems/scheduling/matching_coordination_contracts.py`
  - `subsystems/scheduling/matching_notification_contracts.py` — formal matching contact、customer confirmation preview 與 durable notification typed contracts。
  - `subsystems/scheduling/matching_notification_application.py` — 正式月嫂 LINE 意願在客戶尚未決定時允許雙向更正；接受後可通知不承接以產生換人待辦。月嫂互動在原期限內可重用（含舊 consumed），客戶互動仍一次性；逐次鎖定 current plan、核對本人並追加原版本 writer 的事件。
  - `subsystems/scheduling/matching_plan_workflow.py`
    - 單一已願意初步候選的推薦建立借用 inquiry availability 檢查原詢問期間，預計說明日期不成為阻擋；多月嫂正式分段與後續真正排班仍沿既有正式日期檢查。
  - `subsystems/scheduling/matching_communication_workflow.py` — 正式媒合方案的 LINE 意願、暫停、恢復與取消溝通事件。
  - `subsystems/scheduling/segmented_availability_query.py`
  - `subsystems/scheduling/segmented_availability.py` — 純分段 availability；actual conflict 阻擋完整組合，buffer 只提醒。
  - `subsystems/scheduling/candidate_contact_pool_workflow.py` — 初步候選加入及聯絡 fresh-read 預計期間 availability；一般寄送與重聯絡都使用 current Orders 起訖日，期間變動時借用既有 contact period／fingerprint 更新及前後事件，與預覽使用同一範圍並保留歷史，不建立正式服務日期。衝突候選仍可協調。每週 Preview 核對約定天數並顯示 actual／buffer 提醒。
  - `subsystems/scheduling/matching_line_cards.py` — 候選資訊與正式媒合的 pure Flex renderer。
  - `subsystems/scheduling/proposed_weekly_service_projection.py` — 候選與 proposed formal plan 的 Monday–Sunday 工作日投影；current confirmed service dates 優先於偏好週休，不讀 effective schedule。
  - `ui_react/src/components/OrderInformationSheets.tsx` — 前段每週說明嵌入 Orders-owned 預計日期保存介面；週休選項即時試算但不保存，寄送讀 current 事前服務日期。
  - `ui_react/src/api/scheduling/candidate_contact_pool_client.ts` — weekly GET 讀保存日期；同一路徑 POST Preview 接受當次日期，經 Orders Preview 驗證後零寫入投影每週時數。
  - `subsystems/scheduling/customer_confirmation_download.py` — 由 confirmation package 簽發、到期即失效且檔案範圍受限的客戶履歷下載 reference。
  - `subsystems/line/candidate_contact_postback_application.py` — 將候選資訊卡片回覆轉交給 recipient-bound owner adapter。
  - `subsystems/line/candidate_contact_response_application.py` — 驗證 candidate/customer LIFF recipient，追加結構化回應並建立直接協調 delivery task。
  - `subsystems/line/candidate_contact_coordination_worker.py` — 以 provider sent time 處理 24 小時逾期、willing short-circuit、全池完成後的調整彙整，以及「非空已聯繫池全員終結、零調整條件或客戶已回覆可以／無法調整」的工會人工跟進衍生查詢與一次性群組通知；另投影 exact accepted adjustment、受影響候選與 post-answer Orders Terms receipt gate，供工會完成正式修改後再重新詢問月嫂。
    - 掃描、取消與工會 LIFF 操作共用 service-before-replacement 的 current R-04 資格；過濾於批次上限之前。worker 於 delivery 前執行，保留仍有效 R-04 通知、取消失效案件尚未投遞的人工跟進。
  - `subsystems/scheduling/historical_pending_deposit_matching.py` — Historical Adoption 可用的 typed proposed-plan writer port。
- `subsystems/scheduling/matching_coordination_workflow.py`
- `subsystems/scheduling/matching_notification_application.py` (zero-pool client decision response owner)
- `domains/scheduling/matching_communication.py` — 純媒合意願、客戶決策與送達規則；受信任人工通知允許追加意願更正，LINE 回覆維持原一致性 gate。
  - `subsystems/scheduling/matching_coordination_application.py` — P3 typed leave/date handoffs
  - `infrastructure/mysql/matching_coordination_repository.py`
  - `infrastructure/mysql/matching_coordination_facts_adapter.py`
  - `infrastructure/mysql/historical_pending_deposit_matching_repository.py` — 借用 caller transaction 寫入可由 active Matching Query 讀取的正式 plan／segment roots。
  - `infrastructure/mysql/segmented_availability_repository.py` — fresh-read Client-owned 地區／`clients.service_type`、Staff-owned `staff_regions`／`staff_weekly_rest`，供兩項提示；不再查詢料理、時數或數字偏好，保留原 facts 與正式檔期資格。
  - `infrastructure/mysql/candidate_contact_pool_line_reply_repository.py` — 以已送出資訊事件和 staff LINE identity 重新驗證回覆後，追加意願事件；原 24 小時內本人可用新事件更正自己的意願，current projection 採每位候選最新回覆，其他候選已願意時仍拒絕。
  - `infrastructure/mysql/matching_notification_repository.py` — current Stage 5 confirmation package 的 plan/履歷/order-information/proposed-weekly preflight projection。
    - 同案 active 候選的詢問期間涵蓋區段時，原 willing／unwilling 供無正式回覆區段唯讀使用；已有正式回覆優先，不新增同意或送達事件。
  - `infrastructure/mysql/matching_recommendation_repository.py` — 候選月嫂與占用日期的 read adapter；LINE 收件人只採 canonical bound staff identity。
- entrypoints:
  - `api/routes/caregiver_segment_availability.py` — 候選詢問 `/candidate-contact-pool/availability/search` 與正式分段查詢分離；詢問只接受單人查詢。
  - `api/routes/line_candidate_contact.py`、`api/schemas/line_candidate_contact.py` — recipient-bound candidate/customer query/submit contract 與 LIFF page。
  - `api/routes/line_mobile_admin.py`、`line/static/mobile_admin.html` — 工會媒合人工跟進清單、通知狀態及正式排班工具入口；`system_admin` 綁定者可在同一 LIFF 先經 Orders Terms Query／Preview／Apply，再以 server-verified receipt gate 預覽及重送受影響原候選，初次搜尋零候選不列為通知待辦。
  - `line/static/candidate_contact.html`、`line/static/candidate_contact_customer.html` — 月嫂結構化回應與客戶直接協調介面；LINE identity 只來自 verified ID token。
  - `ui_react/src/api/scheduling/matching_candidate_workflow_client.ts`、`ui_react/src/components/OrderCandidateQueryPanel.tsx` — 待辦工作台初步候選查詢走預計期間入口；多月嫂正式查詢仍走原入口。
  - `ui_react/src/components/OrderCandidateContactStatusPanel.tsx`、`ui_react/src/components/OrderFormalRecommendationPanel.tsx` — 客戶名冊接任續辦重用既有操作；可回報草稿／pending command 給外層關閉保護。候選保存與意願異動後正式推薦刷新 current 候選，推薦不等於正式指派。
  - `ui_react/src/components/OrderRecommendationReplacementPanel.tsx` — 推薦頁統一換人入口；無正式指派借用原 Release／Cancel／Create writer，每步原鍵與回條保留；已有指派重用 RPRE，已服務轉介代班。單一換人原因，不捏造 evidence。
  - `api/routes/matching_coordination.py`
  - `api/schemas/matching_coordination.py`
  - `ui_react/src/api/matching_coordination/matching_coordination_client.ts` — isolated-tested transport client; no current App route consumer.
  - `ui_react/src/components/MatchingCoordinationWorkbench.tsx` — isolated-tested workbench; no current App route consumer.
  - `api/routes/matches.py`、`api/schemas/matches.py` — Stage 5 customer confirmation、matching-plan create immutable receipt Query 與到期履歷 download contract。
  - `db/schema_parts/1032_matching_holiday_work_agreements.sql` — 已退休 agreement 的保留資料 schema；不再有 current writer 或精算 readback consumer。
  - `db/schema_parts/222_matching_plan_create_receipts.sql` — fresh-bootstrap immutable receipt root for formal matching-plan create commands; preserve upgrade uses byte-equivalent migration-only part `1039`.
  - `db/schema_parts/1039_matching_plan_create_receipts.sql` — preserve-only byte-equivalent bridge for the same receipt root; it is not a second writer or a fresh-bootstrap table.

## Dependencies
- outbound: `scheduling/staff-availability` — 初步候選與多月嫂可選資料訂閱暫停／取消／恢復成功通知；受保護的操作完成後重查，保留多月嫂分段日期草稿。
- outbound: `staff/staff-roster-profile` — 候選 availability、候選池與正式推薦 contact-state Query 借用 current `staff.union_no`，透過 nullable `staff_union_no` typed projection 呈現；既有推薦從原 contact-state 取得編號，不額外重查候選池。React 人選清單與推薦選單共用公會編號自然排序及「編號 姓名」標籤，不改 mutation、意願或外部寄送內容。
- 候選查詢可沿既有加入 writer 明示更新 active 人選的過期詢問期間；追加 pending 及前後日期事件，保留歷史並重新取得意願，不發送 LINE。

- outbound: `scheduling/waiting-deposit-lock` — 人工或 LINE 的正式客戶接受回覆，在原 UoW 借用 canonical 自動保留；先取得人員占用 mutex，current 日期齊備才保存唯一等待訂金鎖，衝突與配對回覆一同 rollback。
- outbound: `scheduling/service-before-replacement` — 已提交 R-04 收據綁定 current 零指派 generation 時，訂單成立案件可由原候選及客戶確認 writer 續辦；不回寫 Orders lifecycle，不復用舊推薦的客戶決定。
- outbound: `external-integration/line` — 候選三份投遞狀態與 sent time 讀 canonical `line_delivery_tasks`，以 event key／task ID 綁定；保留原 candidate event，不改 LINE writer 或意願 gate。
- outbound: `orders/order-information` — 候選資訊使用命名投影；預覽與寄送共用相同內容，不建立虛構 assignment。
- outbound: `orders/orders` — case/lifecycle boundary.
- outbound: `clients/client-profile` — `clients.service_type` 原文是案件服務方式唯一來源；此 Query 不取得 writer ownership。
- outbound: `staff/case-preference-manual` — 姓名旁的兩項提示使用同一份 `staff_regions`／`staff_weekly_rest` canonical facts；名冊保存後下次查詢直接反映，原值與明確未知狀態經 typed `matching_conditions` 投影，偏好不排除候選或禁止加入。
- outbound: `orders/service-date-confirmation` — 初步候選週說明的當次日期先經 Orders Preview 驗證，保存沿用既有 Q/P/A；客戶寄送內容以 current 日期組成既有不可變快照。
- outbound: `orders/historical-precision-restart` — restarted `訂單成立` 案件可進入正常媒合；已失效且沒有 generation ownership 的歷史 assignment 不再占用候選檔期。
- inbound: API transport invokes typed coordination commands, not direct DB writes. The React client/workbench remain isolated-tested without a current App route consumer；candidate LIFF 與 recipient-bound postback 則為 current live LINE inbound，經 application／adapter 追加 candidate-contact events。
- inbound: `orders/historical-adoption` — 只有 discussion、開始日空白且月嫂唯一可辨識的來源列，才在同一 outer UoW 建立 proposed plan。
- P3 handoff: committed M3 intents carry immutable `LU96-M3-*` source identity and recipient selector; P5 owns delivery task/provider consumption.

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling ownership.
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — matching preference/unavailability facts.

## Verification
- contract: `tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/unit/test_shared_weekly_information.py` — 共用週內容、recipient fingerprint、未保存阻擋及三份紀錄互不覆蓋。
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_matching_canonical_service_capabilities.py` — canonical relation 保存→提示刷新、四項匯入 facts 保留、原值與未知投影、偏好不排除及不讀退役偏好來源。
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/unit/test_matching_plan_create_receipts.py` — immutable command fingerprint, replay, receipt metadata and read-only receipt Query tests.
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/unit/test_recommendation_cancellation_guards.py` — 取消推薦前的 fresh assignment／有效檔期／communication version gate 與零寫入。
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_matching_notification_application_stage7.py` — existing direct test double for `matching_notification_application` manual response protocol.
- test_root: `tests/test_task97_typed_matching_receipts.py` — 既有正式媒合 API response schema、人工回覆 identity 與拒絕未知欄位測試。
- integration_root: `tests/test_caregiver_matching_plan_service.py` — flat legacy public workflow tests remain at this path because their schema lookup is relocation-sensitive; the autouse caller fixture supplies the currently required create-command event key without restoring a production bypass.
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/`
- test_root: `ui_react/src/tests/candidate_contact_pool_client.test.ts`
- test_root: `ui_react/src/tests/matching_plan_communication_client.test.ts` — 既有正式媒合人工回覆與收據識別 transport 測試。
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
- Candidate direct-coordination LIFF、24-hour worker、工會人工跟進 LIFF／群組通知、recipient-bound reply adapter 與 canonical module tests — `source_observed` — current source and architecture-aligned test root.
- Repository test exception — `source_observed` — current flat path with relocation-sensitive schema lookup.

## Change triggers
Reconcile when coordination owner, case lifecycle eligibility, assignment occupancy semantics, package/event contract, presentation hierarchy, API route/schema, persistence adapter or focused test root moves.

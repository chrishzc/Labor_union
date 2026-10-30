# Module: service-start

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
保存月嫂本人服務開始協調結果；正常直接委派正式日期／排班／帳務 writer，拒絕或檔期衝突才形成工會代班待辦。人員選定並詢問意願、單人原群組邀請、加入後由人員保存日期；服務中換人由原案件指定原區段發起，委派既有正式 handover writer。共用同一 result／candidate store 與交易機制支援請假協調結果，leave-v1／handover-v1 envelopes 與 service-start peers 隔離；請假 owner 路由見 leave-substitution。

## Implementation
- `domains/scheduling/service_start.py`
- `subsystems/scheduling/service_start_workflow.py`
- `infrastructure/mysql/service_start_repository.py`
- `infrastructure/mysql/service_start_arrangement.py`
- `subsystems/line/service_start_messages.py` — 共用零副作用訊息格式。
- `api/dependencies/service_start.py`
- `api/schemas/service_start.py`
- `ui_react/src/api/scheduling/service_start_client.ts`
- `ui_react/src/components/ServiceStartSubstituteWorkbench.tsx`
  - `requestId` 深連結獨立查詢該筆需求並核對案件，不依賴待辦分頁、不改選其他事項；`#scheduling?tab=coordination&case_no=<case>&request=<id>` 由既有 SchedulingPage 薄組合，開頁不 mutation。
- `ui_react/src/components/ServiceStartSubstituteWorkbench.css`
- `line/static/staff_order_search.html`
- `line/static/staff_schedule.html`
- `line/static/mobile_admin.html`
- `api/routes/service_start.py`
- `api/routes/line_staff_self_service.py`
- `api/routes/line_mobile_admin.py`
- `db/schema_parts/1054_scheduling_service_start.sql`

- pending todo Query 與 Apply 同樣只接受洽談中、訂單成立、服務中；不列歷史、取消及完成案件，原需求歷史保留。
- React 完成回應須核對同一 request／案件／人員，並透過 `ordersQueryClient.getAssignmentPlan` 回讀正式版本與逐人服務日期後才顯示完成或通知父頁。收到完成回應後的失敗保存只讀恢復標記；一般查詢或重新進頁讀到完成結果時，同樣先將原未明命令轉成只讀恢復。重試讀取原結果及正式排班，不重送異動，成功回讀才同步總數及通知父頁；離開畫面不送出晚到完成通知。

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — SSTART-01～08。
- owner: Scheduling owns decisions, replacement selection and results; Orders owns actual start/lifecycle, Finance owns payment dates, LINE owns group binding/membership/delivery.
- Committed delivery only; no provider call in commands; one outer transaction borrows canonical owner writers.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/service-start/`
- frontend_test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/service-start/`
- layout_status: `custom_current`

## Change triggers
Update when verified staff/union entrypoints, coordination facts, invitation authority, shared transaction or canonical verification roots change.

# Module: service-start

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
保存月嫂本人服務開始協調結果；正常直接委派正式日期／排班／帳務 writer。開工與延期衝突的契約由 Scheduling 擁有，管理員從原案件直接調整排班。服務中換人由原案件指定原區段發起，委派既有正式 handover writer；請假 owner 路由見 leave-substitution。

## Implementation
- `domains/scheduling/service_start.py`
- `subsystems/scheduling/service_start_workflow.py` — 開工確認與合意延期在同一 UoW 共用正式 writer。Savepoint 涵蓋需求建立，檔期衝突回滾該操作後回傳 typed conflict。群組確認只提交 Reply
- `infrastructure/mysql/service_start_arrangement.py` — 提供零寫入合意延期檔期衝突與補助天數守恆預檢 `preview_leave_defer`
- `infrastructure/mysql/service_start_repository.py` — 只列服務中換人待辦。歷史開工與請假需求保留讀回，候選、意願及邀請僅有服務中換人資格；換人意願回覆沿 Reply-only。
- `infrastructure/mysql/service_start_arrangement.py` — 一般案件工會首次儲存班表，同一交易確認服務日期並委派 Assignment Plan 及相關帳務 writer。
- `subsystems/line/service_start_messages.py` — 共用零副作用訊息格式。
- `api/dependencies/service_start.py`
- `api/schemas/service_start.py`
- `ui_react/src/api/scheduling/service_start_client.ts`
- `ui_react/src/components/ServiceStartSubstituteWorkbench.tsx`
  - 僅呈現服務中換人協調與正式班表回讀。排班頁核對舊深連結的案件與需求類別，再呈現換人或導向原案多月嫂排班。
- `ui_react/src/components/ServiceStartSubstituteWorkbench.css`
- `line/static/staff_order_search.html`
- `line/static/staff_schedule.html`
- `line/static/mobile_admin.html`
- `api/routes/service_start.py`
- `api/routes/line_staff_self_service.py`
- `api/routes/line_mobile_admin.py`
- `db/schema_parts/1054_scheduling_service_start.sql`

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — SSTART-01～08。
- `architecture_declared`：開工與延期衝突不建立代班需求、待辦或意願／邀請流程，依 Scheduling §3.3 由管理員直接調整原案排班。`document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md` 擁有頁籤、深連結及退役入口契約。
- owner: Scheduling owns decisions, replacement selection and results; Orders owns actual start/lifecycle, Finance owns payment dates, LINE owns group binding/membership/delivery.
- Committed delivery only; no provider call in commands; one outer transaction borrows canonical owner writers.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/service-start/`
- frontend_test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/service-start/`
- layout_status: `custom_current`
- `test_service_start_mysql.py` 涵蓋群組確認衝突後只提交 Reply、正式 owner 資料維持、多人等待確認、續辦退役及同鍵成功收據讀回。
- `test_service_start_contract.py` 涵蓋換人待辦資格與總數、舊 dates 入口及成功收據。

## Change triggers
Update when verified staff/union entrypoints, coordination facts, invitation authority, shared transaction or canonical verification roots change.

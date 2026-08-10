---
scope: 02_Assignments_Scheduling_Domain
status: verified
verified_at: 2026-08-09
---

# Assignments／Scheduling Domain 規格落地驗證收據

## 追溯依據

- 規格基線：`01_規格基線/02_Assignments_Scheduling_Domain.md`
- 決策／退役記錄：
  - `19_Legacy_Retirement_Wave_1_Decision_Package.md`
  - `36_Durable_Job_Assignment_Plan_Work_Package.md`
  - `47_Scheduling_Payroll_Legacy_Writer_Exit_Inventory_Receipt.md`
- 既有證據：
  - `evidence/2026-08-08_availability_query_port_receipt.md`
  - `evidence/2026-08-08_g13_leave_cancellation_mysql_receipt.md`

## 本次修正

已移除無正式 production caller 的
`subsystems/scheduling/leave_resolution_workflow.py` 及其專屬 HTTP exception
handler。該舊實作仍直接寫入 assignment 與 schedule，與正式的
`LeaveSubstitutionWorkflow`／`MySqlLeaveSubstitutionRepository` 第二套並存，
不符合 generation/effective、outer UoW 與 immutable batch receipt 的唯一 owner
規則。

舊 `assignment-schedules/*/rest-dates*` 路由保留為明確 `410
legacy_leave_schedule_writer_retired`；新測試覆蓋全部五條 retired mutation route。
production source 對舊 workflow 與其 domain error 的 import／引用為零。

## 實作檢查結果

- Assignment Plan 和 Leave/Substitution 都以 Query/Preview/Apply、aggregate version、
  preview fingerprint、idempotency receipt 與外層 MySQL UoW 執行。
- Assignment Plan repository 對 preflight/fresh impacted staff set 採排序 mutex lock，
  並把 effective occupancy、waiting-deposit lock、buffer、assignment/schedule
  replacement、rebuild event 與 receipt 納入同一交易。
- Leave/Substitution 的正式 repository 鎖定 batch header/children，驗證 canonical
  request snapshot、連續 item ordinal、lineage、版本與 fingerprint；replay 僅回傳 receipt。
- Waiting-deposit lock、availability query、matching與 calendar 都維持 typed server
  owner；legacy public mutation route 為 Gone，不回接直接 SQL writer。

## 驗證結果

```text
.venv\\Scripts\\python.exe -m pytest -q [Assignment Plan, Leave/Substitution,
availability, waiting-lock, mutex, calendar, matching tests]
109 passed in 1.32s

.venv\\Scripts\\python.exe -m pytest -q \
  tests/test_assignment_plan_durable_mysql_e2e.py \
  tests/test_g13_staff_occupancy_mutex_disposable_mysql_e2e.py \
  tests/test_g13_leave_cancellation_disposable_mysql_e2e.py
3 passed in 26.94s

.venv\\Scripts\\python.exe -m pytest -q \
  tests/test_writer_inventory_v3_dispositions.py \
  tests/test_admin_command_repository_source_access.py
4 passed in 1.46s

.venv\\Scripts\\python.exe scripts\\validate_writer_inventory_v3_dispositions.py
writer_inventory_v3_disposition records=658 approved_to_remove=0
```

MySQL 端到端測試只使用暫時的 `mysql:8.4` 容器、localhost `127.0.0.1:33306` 及
`lu_test_scheduling_e2e`；容器已停止並以 `--rm` 自動移除。結果涵蓋 Assignment Plan
same-key durable replay／expired lease recovery、相反月嫂鎖定順序的 mutex 競爭，及
Leave/Substitution 與 Orders Cancellation 對共享 occupancy 的序列化。

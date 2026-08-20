---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260816-react-admin-phase3b2-leave-substitution-public-contract-uow-gap
date: 2026-08-16
owner: Scheduling / Leave Substitution Integration Owner
domain: Scheduling / Orders / Client Finance / Payroll / LINE Delivery
source_work_package: PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions
successor_proposal: PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow
approval_required: human-exact-successor-work-package-before-production-change
---

# Phase 3B2：Leave／Substitution public contract 與單一 UoW 缺口包

## 0. 狀態與結論

Phase 3B fresh contract audit 證明現行 Leave／Substitution 不可直接接 React。此文件只保存缺口、
候選修復範圍與 successor acceptance，不授權 production code、DB、schema、migration、LINE 外送或
React mutation。

Exact backend-first successor 已提出於
`PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow-work-package.md`；其狀態仍為
`proposed`，必須取得文件指定的 exact 人工核准。

## 1. Business scenario 與不可破壞邊界

服務中月嫂請假後，內部人員必須先取得 canonical assignment facts，預覽代班或順延的 Orders、
Scheduling、Client Finance 與 Payroll 影響，再以同一 command Apply。若 Apply 同時承接一筆 LINE
請假申請，正式排班 receipt、請假申請 resolution 與通知 outbox intent 必須在同一 outer transaction
中成立；不得出現排班已提交、但請假待辦仍未解決或通知意圖遺失的 partial success。

外部 LINE provider delivery 不在此 transaction 內，只能由已提交 outbox／durable task 執行。

## 2. Current live-drift

1. `api/schemas/leave_substitution.py` 的 `client_finance_impact`、`payroll_impact`、`orders_impact`
   仍為 `dict[str, Any]`，違反 public typed contract 與 React strict decoder boundary。
2. `api/routes/leave_substitution.py` 先呼叫 `application.apply()` 完成正式 scheduling transaction，
   之後才在 `_resolve_linked_leave_request()` 開第二個 `MySqlUnitOfWork`，解析 leave request 並 enqueue
   LINE task；第二段失敗會留下不可接受的 partial success。
3. linked request 的 expected version、receipt linkage、notification intent 尚未成為正式 Apply command
   與 receipt 的一部分。
4. linked route path在未import `fingerprint_payload`的情況下呼叫它，且在Apply commit後才檢查
   `expected_leave_request_version`；這不是只補import可接受的修復，route-side第二UoW必須移除。
5. LINE request使用`datetime.now()`參與fingerprint，exact replay會重跑resolver/enqueue並產生不同payload；
   同key可能變成idempotency conflict。Receipt SELECT又未讀取strict`result_snapshot`，無法安全replay linked result。
6. workflow generic catch會吞掉MySQL 1205/1213，使公開503/retryable分支實際不可達。
7. route 使用 `require_system_admin`；與現行「所有 enabled internal users 具有相同 business
   capability」政策的對齊尚缺 public route tests，不能由 React client自行推定。

## 3. Successor Work Package 必須裁決

- 四個 impact view 的 exact typed fields、nullable、owner、version lineage 與 redaction；
- linked leave request是正式Apply command的optional nested intent；id/version必須成對並進入fingerprint、
  request snapshot與receipt。日期／case coverage另由
  `PROV-20260817-react-admin-phase3b2-leave-request-date-coverage-decision-gap`裁決；
- 單一 outer UoW owner，以及 Scheduling、leave intake、LINE outbox repository 如何共用同一 connection／lock；
- replay 時同一 key／同一 payload如何回傳同一 receipt，payload mismatch 如何 fail closed；
- notification enqueue 失敗的 transaction semantics；provider delivery failure只能更新 delivery task，
  不得回滾已提交 Domain facts；
- `require_system_admin` 是否保留、替換或映射至 current internal principal policy；
- React SchedulingPage 的 Query／Preview／Apply／receipt／re-query state machine 與 controlled-data browser gate。

## 4. Candidate exact write set（尚未授權）

- `api/schemas/leave_substitution.py`
- `api/routes/leave_substitution.py`
- `api/dependencies/leave_substitution.py`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `infrastructure/mysql/leave_substitution_repository.py`
- `infrastructure/mysql/staff_leave_intake_repository.py`
- `subsystems/scheduling/staff_leave_intake_workflow.py`
- `subsystems/scheduling/leave_substitution_linked_request_resolution.py`（new）
- `tests/test_leave_substitution_workflow.py`
- `tests/test_line_staff_leave_request_schema.py`
- 新增 route／transaction／replay focused tests（successor late-bind exact filenames）
- 後端 freeze 後才可建立 `ui_react/src/api/leave_substitution/`、adapter、SchedulingPage flow tests。

若修復需要 shared exception handler、DB schema、migration 或改變正式 Domain state machine，successor
必須再次縮限 write set 並取得新的人工明確核准；不得由本 gap package 自動擴張。

## 5. Acceptance（successor proposal baseline）

1. Preview 完全零寫入；四個 impact 均為 strict typed view，無 raw dict。
2. Apply fresh-read／lock，正式 scheduling receipt、linked request resolution、LINE outbox intent 只有一個
   outer commit owner；任一內部步驟失敗全部 rollback。
3. exact replay 回同一 receipt；payload mismatch、stale version／fingerprint與corrupt snapshot fail closed。
4. route auth、success、typed 404／409／422／503、redaction、malformed request boundary有focused tests。
5. 真實 disposable MySQL 驗證 transaction rollback、同命令零重複與 outbox invocation count。
6. React 只能在 backend contract freeze 後施工；Apply timeout 進 `outcome_unknown`，先查 receipt，不能換 key。

## 6. DB gate

本 gap package 沒有 DB write set：Scope gate `PASS`；Change Inventory `PASS`（successor可使用既有
request/link/LINE-task/receipt snapshot欄位，0 schema/seed/backfill/destructive）；其餘`NOT_RUN`。
結論：`DB_CHANGE_NOT_READY`。

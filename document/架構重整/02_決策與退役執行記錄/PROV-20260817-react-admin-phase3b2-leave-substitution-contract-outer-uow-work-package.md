---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow
date: 2026-08-17
owner: Scheduling / Leave Substitution Integration Owner
domain: Scheduling / Orders / Client Finance / Payroll / LINE Delivery
source_gap: PROV-20260816-react-admin-phase3b2-leave-substitution-public-contract-uow-gap
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS
activation_state: blocked-prerequisites
approval_required: 核准此 exact Phase 3B2 Leave/Substitution public contract and outer-UoW Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3B2：Leave／Substitution public contract 與 outer UoW 工作包

## 0. 狀態與完成定義

本包已於2026-08-17取得exact人工核准，但只在Scenario Lineage、Global Error Boundary與Phase3B1均PASS後
才能啟動。核准範圍只修後端 public contract 與單一 outer Unit of Work；不接 React、不改
正式 Domain state machine、不改 DB/schema/migration，也不執行 LINE provider delivery。

完成只代表 backend contract／transaction ready。React Scheduling Query→Preview→Apply→receipt→re-query
必須另立工作包。

## 1. Frozen scenario

Controlled input固定來自`validation/scenarios/react_admin_leave_substitution.json`與其fixture/expected
lineage；缺少時不得啟動transaction writer。

Current activation固定`BLOCKED_PREREQUISITES`：上述scenario JSON及其fixture／expected／future receipt
lineage已於2026-08-17完成metadata gate，但Global Error Boundary與Phase3B1尚未PASS。Approval本身不繞過此gate。

一筆服務中請假以同一 command 建立 substitution/extension outcome 時，Scheduling、Orders、Client Finance、
Payroll impact、linked leave request resolution、LINE delivery intent與terminal receipt必須共用同一 outer
transaction。任何內部 persistence 失敗全部 rollback；真正LINE外送只由commit後的durable task執行。

## 2. Public contract

- 維持既有 assignments GET、Preview POST、Apply POST routes。
- 三個跨域impact不得再用`dict[str, Any]`；G1 矩陣必須逐欄凍結 Orders、Client Finance、
  Payroll 的 exact view，不得使用「至少」或任意 extension bag。
- linked leave request id、expected version、accepted state、original outcome staff relation是Preview／Apply command、
  canonical fingerprint與receipt的一部分，不得留在route post-commit side effect。
- Preview／receipt使用nullable typed linked-request view：request/version/status/receipt linkage與
  `not_requested | enqueued` notification intent；不得回LINE provider delivery結果。
- typed errors使用Global category/code/message/correlation/field errors/blockers/retryable/current version。
- 刪除或停止輸出本route-local含`dict[str, Any]`的`TypedErrorView`；所有non-2xx只走已凍結Global
  `detail.error` boundary，linked intake error先在Subsystem映射成typed scheduling error，不得交給legacy adapter猜字串。
- Preview與Apply共用的command request model以Pydantic after-validator強制`leave_request_id`與
  `expected_leave_request_version`同時存在或同時缺失；兩欄必須先進Preview fingerprint，再由Apply原樣帶入。
  route validation失敗時application零呼叫。禁止只在Apply body補linked identity，使Preview／Apply成為不同命令。
- Staff leave request aggregate沒有canonical `case_no`。本包不得宣稱它原本屬於該case，也不得自行推導
  日期／coverage predicate；相關人工裁決記錄於
  `PROV-20260817-react-admin-phase3b2-leave-request-date-coverage-decision-gap.md`。
- 三個public impact summary固定只含`expected_version`、`resulting_version`、lowercase-64hex
  `fingerprint`與`blockers[]`；不得穿透internal payload。需要更多欄位時另經G1逐欄owner/redaction裁決。

## 3. Exact production write set

- `api/routes/leave_substitution.py`
- `api/schemas/leave_substitution.py`
- `api/dependencies/leave_substitution.py`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `subsystems/scheduling/leave_substitution_linked_request_resolution.py`（new）
- `infrastructure/mysql/leave_substitution_repository.py`
- `infrastructure/mysql/staff_leave_intake_repository.py`
- `subsystems/scheduling/staff_leave_intake_workflow.py`

## 4. Exact test write set

- `tests/test_leave_substitution_workflow.py`
- `tests/test_line_staff_leave_request_schema.py`
- `tests/test_staff_leave_intake_workflow.py`
- `tests/test_leave_substitution_router.py`（new）
- `tests/test_leave_substitution_public_contract.py`（new）
- `tests/test_leave_substitution_outer_uow_disposable_mysql_e2e.py`（new）
- `tests/test_g13_leave_cancellation_disposable_mysql_e2e.py`
- `tests/test_order_auto_completion_disposable_mysql_e2e.py`

明確不改 `line_delivery_task_repository.py`、Domain、React、Streamlit、provider worker、shared handler/Auth、
DB/schema/dependency。若現有tables不足，固定`DB_SCOPE_REQUIRED`，不得自行建migration。

`infrastructure/mysql/line_delivery_task_repository.py`、`shared_kernel/clock.py`、`shared_kernel/errors.py`與
Global handler皆為read-only dependencies。Route、repositories、impact ports及linked resolver不得commit；
`LeaveSubstitutionWorkflow`是唯一UoW/commit owner。

## 4.1 Integration document write set

- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包與`02/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow/`（new）

只由Integration Owner於production freeze後更新；其他lane不得競寫。

## 5. 串行與平行分工

- Contract Scout（Luna，唯讀）可先產出逐欄矩陣。
- Backend Owner（Primary）串行擁有route/schema/workflow/repositories；這些transaction hotspots不得拆給多人。
- Test Writer（Terra）只在backend interface freeze後寫四個test paths。
- Auditor（Luna，唯讀）跑scope/raw-dict/commit/provider/tests掃描。
- Integration Owner唯一寫正式規格、README與evidence。

## 6. G0–G7

- G0 exact approval、dirty baseline、0 DB/React/provider mutation。
- G1 strict impact/linked request/receipt/error matrix frozen。
- G2 route不存在post-Apply第二UoW；所有內部writes只有一個commit owner。
- G3 Preview零寫；Preview／Apply共用request pair-validation先於application。Apply 必須先 fresh lock、驗證 linked request
  accepted state／version／original outcome staff relation、再產生
  Scheduling/Orders/Finance/Payroll impacts、resolution、LINE intent、receipt，最後且只 commit 一次；
  staff/link mismatch零寫。禁止先 `application.apply()` commit 後才驗 linked request。
- G4 任一persistence point與LINE enqueue失敗皆全部rollback。
- G5 same-key/same-payload同receipt；actor/reason/version/payload mismatch fail closed。
- G5b LINE task identity、scheduled-at 與 payload fingerprint 由 command/receipt 穩定派生，不得在
  replay path 使用 `datetime.now()` 製造新 payload；same-key replay 不得重複 enqueue。
- G6 disposable MySQL證明atomicity、replay、lock order、outbox intent count；skip即BLOCKED。
- G7 auth／403/404/409/422/503 typed contract、UTF-8、diff、PII/secret與full diff audit。

G3/G4負向矩陣必須覆蓋Preview無pair、有完整pair、半組pair 422、linked snapshot影響Preview fingerprint、
stale leave-request version、LINE enqueue failure與first-command replay。每一失敗點都要斷言Scheduling、Orders、
Client Finance、Payroll、linked resolution、LINE task及immutable receipt零partial write；並以測試證明現行route-level
第二UoW與`datetime.now()`路徑在候選修正前會被拒絕，而不是只掃描字串。

Transaction順序固定：route parse/pair-validation → workflow開唯一UoW → case/staff mutex、command claim與
replay locks → linked request `FOR UPDATE`及state/version/staff驗證 → fresh facts/preview fingerprint →
Scheduling/Orders/Finance/Payroll writes → linked request resolve＋durable LINE task enqueue → 建立含linked view的
完整receipt → immutable receipt snapshot → single commit。任一點失敗全部rollback；provider delivery不在transaction。

Linked intent必須納入Preview/Apply request、command fingerprint、batch`request_snapshot`與replay equality。
Fresh Apply的LINE scheduled time由injected`BusinessClock`取得；exact replay只讀immutable receipt，零resolve、
零enqueue。既有receipt`result_snapshot`保存strict linked result：`request_id/expected_version/
resolved_version/status/receipt_key/notification_intent`；repository SELECT同時讀取並strict驗證
`request_snapshot`與`result_snapshot`。missing/extra/mismatch固定`invalid_batch_replay_snapshot`且零補寫。

Workflow不得以generic `except Exception`吞掉MySQL 1205/1213；transient operational error必須讓唯一UoW rollback，
並由typed boundary回503/unavailable/retryable與`Retry-After`。Capability本包只回歸現有
`require_system_admin`；enabled-user政策另列`CAPABILITY_POLICY_DECISION_REQUIRED`，不得私改Auth。

## 7. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase3b2-leave-uow -q `
  tests\test_leave_substitution_workflow.py `
  tests\test_line_staff_leave_request_schema.py `
  tests\test_staff_leave_intake_workflow.py `
  tests\test_leave_substitution_router.py `
  tests\test_leave_substitution_public_contract.py `
  tests\test_leave_substitution_outer_uow_disposable_mysql_e2e.py `
  tests\test_g13_leave_cancellation_disposable_mysql_e2e.py `
  tests\test_order_auto_completion_disposable_mysql_e2e.py
git diff --check -- api/routes/leave_substitution.py api/schemas/leave_substitution.py api/dependencies/leave_substitution.py subsystems/scheduling/leave_substitution_workflow.py subsystems/scheduling/leave_substitution_linked_request_resolution.py subsystems/scheduling/staff_leave_intake_workflow.py infrastructure/mysql/leave_substitution_repository.py infrastructure/mysql/staff_leave_intake_repository.py tests/test_leave_substitution_workflow.py tests/test_line_staff_leave_request_schema.py tests/test_staff_leave_intake_workflow.py tests/test_leave_substitution_router.py tests/test_leave_substitution_public_contract.py tests/test_leave_substitution_outer_uow_disposable_mysql_e2e.py tests/test_g13_leave_cancellation_disposable_mysql_e2e.py tests/test_order_auto_completion_disposable_mysql_e2e.py
```

## 8. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | proposed且required scenario/prerequisites未PASS |
| Change inventory | PASS | 使用既有tables/result_snapshot；0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 必須由disposable MySQL取得 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

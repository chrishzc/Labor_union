---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260822-react-admin-phase3b1-staff-end-pause-successor
date: 2026-08-22
owner: Scheduling Staff Availability / React Integration Owner
domain: Staff Availability
authority: exact-human-approved-2026-08-22
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-react-admin-phase3b1-staff-contract-hardening completed
approval_required: 核准此 exact Phase 3B1 Staff end-pause successor Work Package
db_change: none
---

# Phase 3B1 Staff end-pause successor 工作包

人工核准證據：使用者於2026-08-22明確回覆「核准此 exact Phase 3B1 Staff end-pause successor Work Package」。
本核准只涵蓋本包Exact write set與Acceptance，不擴張Non-goals。

## Business scenario與owner裁決

公會內部已登入且enabled的操作者，需要把月嫂目前open-ended `paused_service`期間，以明確resume date結束；
resume date本身恢復可接案，server保存的期間結束日為resume date前一日。Scheduling Staff Availability是唯一
owner；React只選取server Query回傳的active paused block並執行Query → Preview → explicit Apply → receipt →
re-query，不自行修改Staff master、assignment、waiting lock、buffer或Matching結果。

本包採正式規格`24_Staff_Matching_Preferences與不可服務期間正式規格.md`既有裁決：所有已登入且enabled的
內部使用者功能權限相同，仍保存actor與audit。`api/routes/staff_availability.py`、
`StaffAvailabilityWorkflow`及repository現有`end_pause`能力先視為candidate contract；writer開工前須fresh
驗證其typed fields、outer UoW、mutex、fresh version、fingerprint、replay與rollback，不得因live code存在反推PASS。

## Scope

- 只啟用`staff.availability.end-pause`。
- 只允許選取current Query中`kind=paused_service`、`status=active`且`end_date=null`的block。
- Preview payload固定為`action=end_pause`、selected `block_id`、`resume_date`與非空reason；不得帶另一Staff的block。
- Apply使用server `source_version`／`preview_fingerprint`與stable Idempotency-Key；timeout／503結果未明時只能以
  完全相同payload/key重試。
- receipt後必重新Query；只有觀察到同一block的server terminal state及server end date才顯示完成。

## Non-goals

- 不包含preference definition administration、long leave／pause create/cancel重作、Staff master CRUD、料理能力
  mutation、special notes、銀行、證照、附件、retirement/reactivation或LINE。
- 不新增schema、migration、seed、backfill或production/provider side effect。
- 不放寬auth，不用前端推算resume結果，不用alert／confirm／prompt或local fake success。

## Exact write set

- `ui_react/src/pages/StaffPage.tsx`
- `ui_react/src/pages/StaffPage.css`
- `ui_react/src/adapters/staff/staff_availability_adapter.ts`
- `ui_react/src/api/staff_availability/staff_availability_schemas.ts`（只在candidate strict contract缺欄時修改）
- `ui_react/src/api/staff_availability/staff_availability_errors.ts`（只在typed mapping缺欄時修改）
- `ui_react/src/api/staff_availability/staff_availability_client.ts`（只在現有generic Preview／Apply無法安全承接時修改）
- `ui_react/src/tests/fixtures/staff/staff_availability_contract_fixtures.ts`
- `ui_react/src/tests/staff_availability_client.test.ts`
- `ui_react/src/tests/staff_availability_flow.test.tsx`
- `ui_react/src/tests/staff_action_race_guards.test.tsx`
- `ui_react/src/tests/staff_control_contract.test.tsx`
- `ui_react/src/tests/staff_no_fake_mutation.test.tsx`
- `ui_react/src/tests/staff_request_budget.test.tsx`
- 本工作包及其專屬`03` evidence directory。

Backend/domain/subsystem/repository檔案不在write set；若fresh preflight發現candidate contract不符合正式規格，
固定新增backend gap／successor並停止React writer，不得在本包偷偷擴張。

## Acceptance

1. G0列出selected Staff、active open-ended pause、source version、operator、resume date、reason與write-set ownership；
   target block缺失、非active、非paused_service、已有end date或屬另一Staff均fail closed。
2. strict client拒絕unknown extra、null／缺失required fields與錯誤enum；每call fresh memory bearer，無token零fetch。
3. Preview零寫入；Apply前重新鎖staff occupancy mutex並fresh-read version／target block／assignment／waiting／buffer
   roots，stale或conflict回typed error，不能以UI覆蓋。
4. Apply只有一個outer UoW；event、aggregate version、receipt與audit同交易；任一失敗完整rollback。
5. same-key/same-payload replay回同receipt；same-key/different-payload回idempotency mismatch；timeout／503只提供同
   payload retry，不宣稱成功。
6. UI狀態至少包含query_ready、preview_ready、apply_pending、outcome_unknown、stale/conflict、observed；pending
   native disabled，field／staff／tab變更清除舊Preview與key。
7. post-Apply re-query觀察同一server block已封閉才顯示完成；UI不自行計算end date或恢復Matching資格。
8. focused backend candidate-contract tests、React focused tests、build、strict UTF-8/no BOM與scoped diff check PASS。
9. Browser controlled scenario覆蓋success、same-key replay、stale、rollback與結果未明；依AGENTS 3.2使用
   allowlisted development `lu_test_*`及scenario-owned rows，保存before/after/receipt/scoped cleanup；不要求
   non-root或disposable DB。HTTP API驗證使用`api-test-workflow`；browser／workflow自身不可用時如實標記
   `BLOCKED_TOOLING`，不得重開production writer或反覆建立DB。
10. 其他Staff controls繼續native disabled；本包完成不授權Phase 5 entry switch。

## DB gate

| Gate | Status | Evidence / reason |
|---|---|---|
| Scope | PASS | 2026-08-22 exact人工核准；只限本包write set |
| Change inventory | PASS | schema/system-seed/business-row-backfill/destructive皆0；僅owned runtime rows |
| Static release | NOT_RUN | 0 schema change |
| Descriptor | NOT_RUN | 0 DB object |
| Read-only plan | NOT_RUN | 無migration |
| Engine verification | NOT_RUN | 待以allowlisted development `lu_test_*` controlled runtime驗收；disposable DB非必要條件 |
| Developer acceptance | NOT_RUN | React focused已開始；API/browser runtime尚未執行 |

固定總結：`DB_CHANGE_NOT_READY`。

## 2026-08-22 candidate preflight

Fresh source audit證明現有Domain／Subsystem／FastAPI與React generic client已涵蓋end-pause candidate contract；
focused Python `5 passed`、React `2 files / 8 tests PASS`。因此核准後預設只啟動React/page/tests writer，
backend/domain/subsystem/repository不進write set。此結果不構成production authority或runtime PASS；browser／DB
均未執行，control仍native disabled。

## 2026-08-22 frontend checkpoint

最新人工營運前端優先序下，React已依本包核准範圍啟用server-gated end-pause：只有selected Staff的
`paused_service`／active／open-ended block、resume date與非空reason齊備時Preview才可操作；Apply仍須同一
server Preview payload。先前盤點所稱「end_pause應維持全域disabled」已被本exact approved successor取代，
不得再用舊結論鎖回控制。

Staff日期邊界另校正為`Asia/Taipei` BusinessClock呈現；UTC `2026-08-22T16:30:00Z`必須送出
`as_of=2026-08-23`。目前focused React 7 files／29 PASS、production build PASS。fixture gate已通過；本包仍維持
`in-progress`，因`lu_test_*` API/browser success、replay、stale、rollback、outcome-unknown與工會主機真實資料
均尚未執行，不構成production authority或Phase 5 switch。

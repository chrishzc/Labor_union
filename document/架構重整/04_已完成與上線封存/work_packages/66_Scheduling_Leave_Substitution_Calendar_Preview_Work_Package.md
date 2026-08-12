---
doc_type: work-package
declared_status: completed
priority: P0
owner: Assignments / Scheduling
approved_at: 2026-08-12
updated_at: 2026-08-12
---

# WP66 Scheduling 休假代班 Calendar Preview

## Business scenario

管理員建立休假、順延或代班草稿後，系統必須以正式 Scheduling facts 產生零寫入的
before／after Calendar Candidate。跨 Domain blocker 不得遮蔽候選，但必須使 Apply fail closed；
只有管理員確認且 Apply 重新讀取最新 facts、版本及 fingerprint 後，才可在單一交易提交。

## Scope

- Preview 回傳 typed day cells、服務日數守恆與獨立 `apply_readiness`。
- 代班維持同日服務並顯示原／新 staff；順延顯示移出及移入日期。
- UI 只 render 後端 candidate；readiness blocked 時停用 Apply。
- Apply 保留既有 fresh-read、lock、idempotency、outer UoW 與 rollback。
- focused Module／Subsystem／API／UI tests 與實際 UI 驗收。

## Write set

- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `api/schemas/leave_substitution.py`
- `api/routes/leave_substitution.py`
- `ui/pages/scheduling/leave_substitution_panel.py`
- `ui/pages/03_calendar.py`
- `ui/pages/scheduling/case_staffing.py`
- `ui/pages/scheduling/assignment_plan_panel.py`
- `ui/api_clients/leave_substitution_api_client.py`
- `infrastructure/mysql/leave_substitution_repository.py`
- `api/dependencies/leave_substitution.py`
- `tests/test_leave_substitution_workflow.py`

## Out of scope

- LINE 月嫂請假申請、月嫂配對、production DB／deployment。
- Preview 自動建立 Client Finance／Payroll roots。
- 新增 Calendar snapshot schema 或由 UI 重算業務日期。

## Acceptance

1. Preview 零寫入並可回傳 before／after day cells。
2. Domain blocker 存在時 candidate 可見、`apply_readiness=blocked`、Apply 停用。
3. 代班不延長服務日；順延維持合約服務天數守恆。
4. Apply 仍 fresh rebuild；blocker、stale、conflict 或 persist failure 全部零部分寫入。
5. UI 實際顯示變更日、staff ownership、readiness 與 Apply gate。

## Completion evidence

- `tests/test_calendar_attendance_order_filter.py`、
  `tests/test_leave_substitution_workflow.py` 與
  `tests/test_api_contract_smoke.py`：2026-08-12 focused regression `16 passed`。
- 真實 case `115000008` 的 Preview API 回傳 36 個 day cells；
  `apply_readiness=blocked`，blocker 為 `client_finance_bootstrap_required`，
  `scheduling_leave_substitution_batches` 保持 `0 -> 0`。
- 真實 Chrome UI：案件人力配置選取 assignment `#232`、加入請假項目、
  產生 Preview；顯示 blocker 且 Apply disabled，未觸發 Apply。

Current Scheduling baseline 已承接根事實、Preview zero-write、Apply fresh-read/
lock/idempotency/outer UoW 與 UI thin-client 邊界；此 Work Package 不再保有 active
操作責任。

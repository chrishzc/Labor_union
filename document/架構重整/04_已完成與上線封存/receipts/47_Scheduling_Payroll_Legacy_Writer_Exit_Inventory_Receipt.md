---
doc_type: verification-receipt
authorization: architecture-46-confirmed
verification_date: 2026-08-08
---

# Scheduling／Payroll Legacy Writer Exit Inventory Receipt

## 受檢邊界

本收據僅證明 Writer Inventory 的靜態退出條件，不宣稱刪除尚保留於
`infrastructure/mysql/mysql_adapter.py` 的歷史實作。

Validator 掃描 `api`、`domains`、`infrastructure`、`line`、`scripts`、`services`、
`subsystems` 與 `ui` 的 Python production sources；測試與歷史 system map 不算 runtime
caller。

## Scheduling

下列 legacy mutation 已從 `infrastructure/mysql/mysql_adapter.py` 移除：

- `update_matching_info_sent`
- `mark_resume_sent`
- `mark_resume_sent_for_case`
- `reply_matching_inquiry`

Validator 會以 AST 確認 adapter 不再定義這些函式，並再掃一次所有 production call
expression；發現任何定義或呼叫即 fail closed。正式 replacement 是
`subsystems/scheduling/matching_communication_workflow.py` 的 matching-plan state transition。

## Payroll

Payroll inventory 的 writer 必須只位於 `infrastructure/mysql/payroll_*` 或
`subsystems/payroll/`，並且是 `retain_canonical` 或 `retain_restricted`，且 runtime caller
receipt 必須指向 typed workflow。任何 Payroll `migrate_then_remove`、非 typed caller 或越界
writer 都會使 validator 失敗。

## 仍待後續動作

此 receipt 證明該四個舊 Scheduling mutation 已由 typed owner 取代並移除。舊的 candidate
與 disposition identity 會在重新產生 evidence 時消失；validator 不允許 reconciliation
保留已不存在於 candidate 的 stale record。

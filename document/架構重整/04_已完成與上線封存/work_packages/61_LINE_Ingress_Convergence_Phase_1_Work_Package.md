---
doc_type: work-package
declared_status: completed
date: 2026-08-12
owner: LINE Integration
---

# LINE Ingress Convergence Phase 1 Work Package

## Business scenario

LINE 使用者輸入「服務說明」或客服分類時，canonical webhook inbox consumer 必須把事件交給
Customer Service owning workflow；客服 ticket、audit intent 與 delivery task 必須使用同一
LINE Unit of Work，不得由 adapter 的本地文字回覆取代。

## Authority and scope

本包執行 contract `35_LINE_Ingress_Developer_Experience_Convergence_Contract.md` 的第一個
可獨立切片，並遵守正式規格 `17_External_Integration_LINE_Access正式規格.md` 與
`20_LINE客服與月嫂自助服務正式規格.md`。

使用者指定的 `document/line/服務說明規則書.md` 是本切片服務說明語意與文案的來源；
`history/work_log.md` 僅用於追溯 legacy ingress 的來源與既有裁決，不能覆蓋前述正式規格。

Write set 限於：

- `subsystems/line/webhook_identity_handlers.py`
- `tests/test_line_customer_service_first_release.py`
- 本 Work Package 與完成 evidence/index。

## Non-goals

- 不變更 `LINE_WEBHOOK_RUNTIME_MODE` 或 `LINE_WORKER_RUNTIME_MODE` 的預設值。
- 不進行 production cutover、deployment、schema migration、Rich Menu 設計或 UI 變更。
- 不刪除 legacy webhook runtime、union-staff menu 或 `esc` fallback。
- 不變更既有 identity aliases：`綁定訂單`／`訂單查詢` 為 customer binding，
  `綁定後台帳號` 為 admin binding。

## Required behavior

1. `LineWebhookIdentityHandlers` 有注入 `LineServiceHelpApplication` 時，必須使用其
   `handle`；本地 legacy service-help helper 不得搶走 canonical path。
2. 未注入時才可保留本地 helper 作 legacy-compatible fallback。
3. identity intent 仍優先於 service help，避免既有綁定語意被攔截。
4. focused tests 必須證明 injected application 收到 canonical user identity 與原始文字；
   Customer Service ticket/audit/delivery 的既有 one-UoW test 必須保持通過。

## Acceptance and evidence

- `tests/test_line_customer_service_first_release.py`
- `tests/line/subsystems/test_line_identity_stage4.py`
- `tests/line/subsystems/test_line_runtime_stage3.py`
- 完成後建立 `03_追蹤清單與證據/evidence/` receipt，回寫本包 status。

## Next phases and blocker

本 Phase 不宣稱完成 contract 35。後續仍需依獨立可核准範圍處理 union-menu／`esc`、
legacy handler characterization、canonical cutover receipt 與 legacy runtime exit。未經新的
release/cutover 授權，不得把 canonical runtime 改為預設或移除 public compatibility path。

## Completion evidence

`../03_追蹤清單與證據/evidence/2026-08-12_line_ingress_phase_1_service_help_receipt.md`
記錄 injected owner workflow、identity-priority regression 與 canonical runtime regression。

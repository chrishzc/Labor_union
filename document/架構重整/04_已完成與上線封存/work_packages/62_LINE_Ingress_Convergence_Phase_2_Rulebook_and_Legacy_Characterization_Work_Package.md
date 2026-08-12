---
doc_type: work-package
declared_status: completed
date: 2026-08-12
owner: LINE Integration
---

# LINE Ingress Convergence Phase 2：規則書對齊與 Legacy Characterization

## Business scenario

一般 LINE 使用者由下方選單點選「服務說明」後，系統必須以 canonical inbox consumer
處理六個分類，且任何 legacy ingress 差異都必須先被定位與測試化，不能以
`line/line_bot.py` 的 direct SQL 或 `line_tasks` insert 作為新功能範本。

## Authority and source trace

- 正式架構：`17_External_Integration_LINE_Access正式規格.md`、
  `20_LINE客服與月嫂自助服務正式規格.md` 與 contract 35。
- 使用者指定的業務語意來源：`document/line/服務說明規則書.md`；其六分類、手動輸入
  aliases、不得直接改客戶資料、客服需求與服務時間語意均需對照正式規格實作。
- 歷史追溯：`history/work_log.md`。它確認 Stage 11 已引入 Customer Service canonical
  workflow，並記錄 union-staff menu 與 `esc` 是 legacy 直接任務模式；歷史紀錄不授權
  恢復任何 direct SQL、internal-key-only mutation 或 query-string identity。

## Fresh inventory and live drift

1. canonical worker 已注入 `LineServiceHelpApplication`，因此 `服務說明` 與六個分類會經
   Customer Service owning workflow、audit 與 durable delivery task。
2. Phase 2 已補 `訂單進度` alias，以及服務流程／收費補助的規則書核准文案回歸。
3. `line/line_bot.py` 的 `union_staff` menu switch 與 `esc` 的 legacy route 已有 payload、role
   guard、queued task 與 redelivery characterization；沒有可直接重用且已核准的 canonical command，
   因此不能移植或刪除。
4. 未綁定「查詢服務進度」已在同一事件建立 short-lived customer identity flow，並以 event ID
   建立 stable idempotency identity；canonical worker 會提供可驗證的 entry URL。
5. 規則書的「連續兩次無法辨識後建立客服需求」需要 durable conversation session；既有
   history 已列為 deferred，沒有 schema／state-machine 授權，本包不實作。

## Scope and write set

- `subsystems/line/service_help_application.py`
- `scripts/run_line_worker.py`
- `tests/test_line_customer_service_first_release.py`
- 本 Work Package、Phase 2 receipt 與 active index。

## Non-goals

- 不更改 canonical／legacy runtime default，不進 production cutover 或 deployment。
- 不新增 conversation schema、客服 SLA、指派、統計或完整對話紀錄。
- 不移植、刪除或恢復 union-menu／`esc`；它們必須先有 owner、typed command、outbox 與
  pre-migration characterization。
- 不變更 identity aliases 或 Rich Menu definition／publication。

## Acceptance

1. 規則書可接受的 Stage 1 aliases 至少有 focused regression，且文案不承諾最終收費。
2. canonical Service Help 的 ticket、audit 與 delivery 維持同一 outer Unit of Work。
3. legacy-only menu commands 的 payload、role guard、durable task 與 redelivery characterization
   已在 receipt 中可追溯；不得藉此宣稱 legacy exit 或 runtime cutover 已完成。
4. conversation session drift 必須明確保留為 active follow-up，而不是以靜態回覆假裝完成。

## Dependencies and next decision

本包已完成 rulebook-parity 與 characterization。完成 contract 35 的全量 legacy migration 前，
仍需要一份人工確認的 conversation-session decision，
以及 union-menu／`esc` 的 business owner 與 desired
canonical behavior。沒有這些決策時，Phase 2 只能完成已授權的 rulebook-parity slice 與
characterization，不能封存 contract 35。

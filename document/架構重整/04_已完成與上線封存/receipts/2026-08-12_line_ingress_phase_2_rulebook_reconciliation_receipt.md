---
doc_type: evidence-receipt
declared_status: completed; rulebook parity and legacy characterization validated
date: 2026-08-12
owner: LINE Integration
---

# LINE Ingress Phase 2：服務說明規則書對照收據

## Sources used

- `document/line/服務說明規則書.md`：服務說明的六分類、手動輸入 aliases、客服邊界與文案。
- `history/work_log.md`：legacy ingress 的歷史來源；僅作追溯，非現行規格。
- `17_External_Integration_LINE_Access正式規格.md`、
  `20_LINE客服與月嫂自助服務正式規格.md` 與 contract 35：目前架構與驗收邊界。

## Validated change

`LineServiceHelpApplication` 已接受 `訂單進度` 作為「查詢服務進度」的手動輸入 alias；
服務流程與收費／補助回覆採規則書文案，明確說明最終金額仍由工會確認，且引導未登記使用者
至服務登記。未綁定者查詢進度時，會以該 inbox event ID 建立 short-lived customer identity
flow，再把可驗證的入口放進 canonical durable delivery task；沒有同步呼叫 LINE API。

Executed:

```text
.venv\Scripts\python.exe -m pytest tests\test_line_customer_service_first_release.py tests\line\subsystems\test_line_identity_stage4.py tests\line\subsystems\test_line_runtime_stage3.py -q --basetemp .pytest_tmp\wp35-rulebook-flow
```

Result after adding legacy characterization: `29 passed`.

## Deliberately unresolved legacy ingress

| Legacy capability | Current source | Reason it remains |
|---|---|---|
| union-staff menu switch | `line/line_bot.py`: direct `line_users.role` query plus legacy task enqueue | characterization 證實它只接受 `union_staff`、建立 `rich_menu_link`、使用 event-key 並在 duplicate event 不重複入列；未有已核准 canonical command／owner，不可從 adapter 直接複製。 |
| `esc` default-menu reset | `line/line_bot.py`: legacy `rich_menu_unlink` task | characterization 證實它沒有角色 guard，會以 event-key 入列 unlink；現有 canonical binding 是已綁定身分／publication outbox workflow，不等同可任意解除 menu。 |
| 連續兩次無法辨識後建 ticket | 規則書第 6 節、merge history | 需要 durable conversation session 的狀態機與 schema，現無核准 write set。 |

因此，本收據不表示 contract 35、legacy runtime exit、runtime default cutover 或 production
deployment 已完成。下一個 executable scope 必須先由人工裁決 union-menu／`esc` 的 canonical
business behavior 以及 conversation session state machine。

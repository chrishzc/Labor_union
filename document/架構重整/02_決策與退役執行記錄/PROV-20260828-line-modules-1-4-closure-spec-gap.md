---
doc_type: implementation-closure-record
declared_status: repository-local-complete
date: 2026-09-01
owner: line-integration / scheduling / customer-service / payroll
canonical_source: 01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md
---

# LINE 模組 1～4 repository-local closure

## Scope

流程圖 M1～M4 的非 FAQ 節點必須使用 current typed owners，不得把 LINE transport變成 Client、Staff、Orders、Scheduling、Payroll 或 Staff Payables writer。使用者已明確排除本輪 LIFF/ngrok UI 驗收；真 provider send也維持 external `not_run`。因此本記錄只判定 repository-local source、local MySQL baseline與可重跑測試，不宣稱 verified LIFF或 provider acceptance。

## Current coverage

| Module | Implemented owner path | Current evidence |
|---|---|---|
| M1 身分／雙角色／生命週期 | role-scoped identity binding、failure streak、review／revocation、Staff retirement、Orders terminal closure→雙角色選單 restore | canonical LINE／Access／Orders tests passed；verified LIFF WebView `not_run` |
| M2 routing／feedback／客服 | server-owned navigation catalog、deterministic confidence／clarification、protected aliases、feedback root／receipt／aggregate、unresolved ticket與human escalation delivery | deterministic／API／repository contracts passed；FAQ內容排除；AI provider `not_run` |
| M3 matching／雙向通知／決策 | matching intent target-owner constraints、staff/client recipient projection、customer decision、zero-pool客服 ticket、matching outbox worker | canonical Matching／LINE tests passed；Scheduling lane C real MySQL completed；true LINE delivery `not_run` |
| M4 safe link／complaint／payables | short-lived single-use link、expiry／revoke／wrong-actor rejection、complaint ingress→hold／HIGH ticket／alert、leave substitution→Payroll→Staff Payables lineage | focused contracts passed；safe-link additive schema fresh bootstrap passed；Scheduling/payables real MySQL lane passed；LIFF/NAS/provider `not_run` |

## Notification baseline

`config/notification_rules.json` 是 canonical non-empty catalog，不再是空目錄。`scripts/bootstrap_line_configuration.py` 在 exact `lu_test_1` 完成：

- 6 種 LINE configuration revision committed；
- 13 個 canonical source events committed；
- canonical identity、trigger、recipient selector、template/rule references受 validation；
- bootstrap natural keys可 idempotent replay。

Notification pending／processing／retryable replay本身不建立 LINE-006；只有 current authoritative failure predicate可建立 issue，成功／人工完成後 recheck會 reconcile/delete。

## Observable failure boundaries

- wrong identity／role／actor、expired／replayed／revoked safe link：typed fail-closed。
- stale owner version／recipient/config drift：停止 mutation，重新 Query／Preview；不 blind retry。
- zero-pool：不自動放寬條件，建立人工作業 criteria／ticket。
- customer reject／delivery terminal failure：保留 owner decision／intent／task／result lineage與 manual fallback。
- provider unavailable：明示 `provider-not-run`；不得把 HTTP 200、queue existence或 mock page當成真外送 receipt。

## Remaining external acceptance

以下不在本次完成範圍，且仍為 `not_run`：verified LIFF/ngrok、真人 password/MFA WebView、真 LINE recipient delivery／Rich Menu publication、NAS media與 production cutover。若日後啟用，必須逐流程補 provider receipt／fresh readback，不需重建 M1～M4 source功能。

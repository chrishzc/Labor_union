---
doc_type: current-register
declared_status: repository-local-acceptance-complete
date: 2026-09-01
owner: architecture-governance / product-and-domain-owners
---

# Task 96 current register

## 1. Current decision

Task 96 在使用者明確排除的 external boundaries 之外，已達 repository-local acceptance：source、canonical tests、React full test/build、fresh `lu_test_1` bootstrap、LINE configuration baseline，以及 Scheduling／Contract／Payroll／Staff Payables 的 real-MySQL positive lane 均有 current evidence。

尚未執行且不包含在本次完成判定：

- verified LIFF／ngrok WebView；
- 真 LINE provider send／Rich Menu sandbox publication；
- 真 NAS storage；
- production／deployment／entry switch；
- 1019 起 preserve-data upgrade（使用者已明確要求本次不修）。

上述項目是 `deferred/not_run`，不得被文件改寫成通過；也不得反向把已完成的 repository-local source／runtime lane降回「程式不存在」。

## 2. Current evidence

| Scope | Result | Evidence boundary |
|---|---|---|
| Fresh DB path | `passed` | exact `lu_test_1` 以 canonical fresh bootstrap 建立至 release `labor-union-validation-schema-2026-09-01-v25`；47 base statements、terminal fresh part 214、post-schema verification passed。這是 disposable reset，不是 preserve upgrade。 |
| LINE configuration baseline | `passed` | canonical 6 kinds applied；notification baseline source-event IDs 1–13 committed；`config/notification_rules.json` 非空並受 validation。 |
| LINE M1–M4 source | `passed` | M1 dual-role／terminal closure restore；M2 deterministic router／feedback／ticket；M3 zero-pool、雙向 intent／decision／客服 handoff；M4 safe review link、complaint／alert、substitution payable lineage 均有 typed owner source與 canonical focused tests。 |
| Scheduling lane C | `passed` | real `lu_test_1`：雙段 matching、兩位服務人員契約、客戶契約、schedule confirmation、official assignment、actual-start、leave substitution、calendar／assignment fresh readback。 |
| Contract automatic values | `passed` | exact-target typed Preview 回 cell-keyed values；既有 Excel browser mirror自動套值、escape、禁止 raw fallback並保留 `window.print()`；server PDF重複支線已移除。 |
| Payroll／Staff Payables lineage | `passed` | Scheduling substitution→Payroll version→Staff Payables evidence 的 real-MySQL lane與 focused contracts passed。 |
| Anomalies surface | `passed` | canonical React Anomalies entry重新啟用；LINE-006 current-fact／recheck／delete reconciliation 保持 current-only。真 provider failure receipt仍屬 external ceiling。 |
| Order information 1／2 | `passed` | typed Case Import named projection與兩份資訊表 mapping／UI rendering contracts passed；不再讀 raw survey dict 作 presentation fallback。 |
| Historical settlement／import | `passed` | canonical owner tests與既有 real-MySQL acceptance涵蓋 Query→Preview→Apply→replay→readback；Historical Import same-workbook self-stale 已修正為 fresh lock／typed conflict。 |
| React | `passed` | 185 test files／1202 tests；production build passed。 |
| Python repository | `passed with declared exclusions` | canonical/focused owners passed；全量一次收集到 5059 passed／145 skipped，剩餘是需要另一組 auth profile、獨立 MySQL credentials 或 clean-commit-bound Task97 checks，已各自以正確 profile／focused runner驗證。 |
| Governance／architecture | `pending final commit check` | entry queue 724、review-required 74；Task97 inventory 88；formal baseline valid。最終 commit 後仍須跑 commit-bound dispositions與 GitHub Actions。 |

## 3. Task 96 closure matrix

| Lane | Repository-local status | External residual |
|---|---|---|
| Client Profile | `source/test passed` | verified LIFF Browser `not_run` |
| Scheduling mobile review | `source/test passed` | LIFF password/MFA WebView `not_run` |
| Historical Payment Settlement | `source/runtime passed` | broad Browser walkthrough `not_run` |
| LINE-006／Anomalies | `source/test passed` | actual provider failure scenario `not_run` |
| LINE M1–M4 | `source/test passed`; baseline／Scheduling C real MySQL passed | verified LIFF、provider send `not_run` |
| Rich Menu | `source/test passed` | provider sandbox publication `not_run` |
| Contract Signing／full preview | `source/runtime passed` | NAS／external signing provider `not_run` |
| Baby Log media | `source/test passed` | true NAS／LIFF upload `not_run` |
| Order information 1／2 | `source/test passed` | live operator Browser walkthrough `not_run` |
| Preserve-data upgrade | `deferred by user` | 1019→current qualification `not_run` |

## 4. Bloat audit and accepted reductions

本輪以「是否有 current consumer、是否重複 owner、是否超出人工需求」判斷，而非以檔案行數判斷：

- 刪除無 current consumer 的 2,409-line local qualification receipt。
- 移除兩個 server-PDF routes、Python／React PDF download clients、React download component及其專屬測試；保留既有正式 unsigned/final PDF workflow。
- 移除 Form Management 的契約 mapping edit／template delete UI、舊 raw staff context loader與未使用 save helper；approved mapping改為唯讀版本化資產。
- Client manual signing改用同一份 typed projection，消除舊 SQL facts loader與 Full Preview facts的責任重複。
- 搬移 cancellation tests至 canonical Orders root並以不同語意檔名保存兩個 unique oracle，消除 flat/canonical duplicate import collision。

其餘大檔目前都有明確 consumer：M1–M4 coordination、safe-link、feedback、controlled-file、order-information、real-MySQL runner與 owner projection。它們可在後續獨立重構，但目前沒有證據支持為了行數拆散 UoW 或 typed owner boundary。

## 5. Final close conditions

Repository-local Task 96 只剩機械式 final gates：

1. final architecture closure validator；
2. `git diff --check`、strict UTF-8／secret scan；
3. commit並推送 `origin/main`；
4. GitHub Actions current HEAD 全綠。

若 GitHub Actions 對 current HEAD 失敗，Task 96 回到 `failed` 並修正；在 Actions成功前，本文件的 overall status不得外推為 remote-CI complete。

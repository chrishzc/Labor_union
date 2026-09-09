---
doc_type: work-package
declared_status: blocked
priority: P1
owner: Import Integration / Global Entry Governance
domain: Finance Import / Case Import / LINE Integration
subsystem: import entrypoint transition and legacy writer retirement
initiative: import-entry-retirement
updated_date: 2026-09-09
implementation_authorization: granted-by-user-2026-08-15-for-scoped-retirement-work-packages
supersedes_scope_from: ADR-001-import-architecture-refactor
---

# 匯入入口與 Legacy Writer 退役工作包

## 1. Current purpose

本包只承接已完成匯入架構後仍未閉合的 entry retirement：確認 Client／Staff historical intake helper 是否仍有合法 consumer，並在 verified-LIFF replacement acceptance 成立後退役 temporary Web／legacy writer。它不重新定義 profile root、匯入資料模型、warning、historical adoption、HCM correction 或 upload lifecycle。

## 2. Current Authority

- `09_Finance_Import_Domain.md`：HCM／帳務日常寫入固定走 authenticated Web typed workflow，不得回退 File Watcher、browser SQL 或 unrestricted CLI apply。
- `17_External_Integration_LINE_Access正式規格.md`：LIFF 身分只信任 server-verified token 與 current binding。
- `20_LINE客服與月嫂自助服務正式規格.md` §6.1：Client／Staff profile mutation 已有 owner、field allowlist、version、Query／Preview／Apply、outer UoW、receipt 與 fresh owner readback contract；LINE Integration只提供 identity／transport，不是 profile writer。
- `19_Global_Entry_Point_Governance.md`：每個 API／CLI／temporary Web／LIFF entry 必須有獨立 caller、replacement、retirement 與 restore-trigger evidence。

因此 Staff profile writer 不再是 Authority blocker；remaining blocker 是 current runtime／verified-token replacement acceptance 與 caller-retirement evidence。

## 3. 已完成且不得重開的 historical slices

- `ARCH-20260815-102`：Finance File Watcher、runtime caller 與 direct dependency 已退役；Finance Web upload 保持唯一日常 writer。
- `ARCH-20260815-103`：Historical Orders retired CLI／direct SQL 已移除；typed Web 與受控 historical adoption path 保留。
- `ARCH-20260815-104`：Finance CLI `--apply` fail closed，只保留 operator-only format diagnostic。
- `ARCH-20260815-105`：HCM legacy CLI entrypoint 已移除。
- `ARCH-20260815-106`：HCM historical service composition／whole-row direct SQL writer 已移除。
- `scripts/imports/reprocess_finance_import_batch.py` 的 apply 在 DB connection 前拒絕，只保留 read-only diagnostic。

這些完成項只由 Git history／current source與tests追溯，不再形成本包施工 queue。

## 4. Remaining bounded work

### A. Client／Staff BeClass dead historical SQL/helper audit

只盤點仍存在的 restricted historical intake CLI／helper、caller與tests。可證明不可達且沒有 current maintenance consumer 的 direct SQL／legacy helper 才可在 owner-bounded slice 退役；仍有合法 restricted historical import consumer 的 adapter 不因名稱含 legacy 就刪除。不得把 historical intake 誤認為 current LIFF writer。

### B. Client temporary Web → verified LIFF replacement acceptance

正式 replacement 依 `20` §6.1／`17`：server-verified ID token → current binding → owner Query → zero-write Preview →人工確認→ Apply → receipt → fresh owner readback。退役 temporary Web 前必須同時具備：

1. current LIFF route／registration可達；
2. verified-token Browser E2E 使用真實 current binding，不接受 client-supplied user ID；
3. Query／Preview／Apply／receipt／readback 依 current Client owner contract通過；
4. caller inventory 證明沒有仍需 temporary Web 的 current caller；
5. Rich Menu／binding／publication若是實際進入該 LIFF 的 prerequisite，必須以 current provider acceptance證明，不以 source green取代。

任一項缺少時保持 `blocked`，temporary Web 不得先行退役。

### C. Staff verified-LIFF profile-writer replacement acceptance

Staff owner、欄位、version與UoW已由 `20` §6.1裁決，不再等待新 Authority。Remaining gate固定為 current schema／test target readback、verified-token Browser E2E、owner Q/P/A receipt、fresh Staff readback、以及 caller inventory／temporary-entry retirement evidence。LINE identity bind只證明身分綁定，不能替代 Staff profile writer acceptance。

## 5. Effect ceiling

本包只允許 entry/caller inventory、retirement guard、dead-helper removal、typed replacement wiring與focused regression。不得藉此修改 owner root、public business contract、schema／migration、provider publication、production DB、deployment或entry switch。若 current replacement 需要新的 schema、public contract或external side effect，必須另走對應 T3／DB／provider gate。

## 6. Completion definition

只有下列全部成立才可把本包標 `completed` 並自 working tree 退役：

- 每個 current import/profile entry 都有唯一 owner與唯一 active writer；
- Client／Staff temporary Web 的 verified-LIFF replacement 已通過 current acceptance，且 caller inventory允許 retirement；
- dead historical SQL/helper 已逐項形成 `remove | retain_restricted` disposition，沒有雙 writer；
- 被移除 entry 有 focused regression、restore trigger與 current source readback；
- 所有仍未完成 external/provider/runtime gate 精確留在新的 current successor，而不是重開本包。

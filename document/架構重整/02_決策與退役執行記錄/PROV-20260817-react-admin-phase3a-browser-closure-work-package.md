---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3a-browser-closure
date: 2026-08-17
owner: LINE React Closure Integration Owner
domain: LINE Customer Service / Identity
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
candidate_baseline_required: PROV-20260816-react-admin-phase3a-line-customer-service-identity implementation present; fresh base-drift audit required
approval_required: 核准此 exact Phase 3A Browser Closure Work Package
ui_execution_mode: controlled-browser-required
production_write_set: none
db_schema_write_set: none
external_provider_mode: disabled-test-adapter-only
---

# Phase 3A LINE Customer Service／Identity Browser Closure 工作包

## 0. Purpose

這是closure gate，不是第二份Phase 3A implementation。只在最新工作樹重新驗證既有客服ticket query/detail／
resolve Preview→Apply→re-query與LINE identity query／revoke Preview→Apply→re-query，補真實兩段式登入、受控資料、
Network↔DOM與回歸證據。不得修改production來迎合測試；若發現契約或程式缺陷，固定回
`BLOCKED_PRODUCTION_SUCCESSOR_REQUIRED`並另立exact修復包。

## 1. Exact write set

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3a-line-customer-service-identity-work-package.md`（只有全部gate PASS時由Integration Owner更新status/evidence）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3a-browser-closure/candidate-change-inventory.md`（new）
- 同目錄`verification-receipt.md`、`browser-smoke-receipt.md`、`open-findings.md`（new）
- 本工作包與`02_決策與退役執行記錄/README.md`（Integration Owner only）

禁止修改`ui_react/src/**`、`api/**`、`domains/**`、`subsystems/**`、`infrastructure/**`、`tests/**`、
`validation/**`、DB/schema、launcher、provider設定或entry queue。原始命令輸出只去敏摘錄至receipt。

## 2. Runtime safety and acceptance

1. 開始前保存branch、HEAD、dirty paths與Phase 3A production/test paths清單；closure前後production bytes完全一致。
2. 使用真FastAPI＋Vite、password challenge→TOTP→memory session；禁止dev token、combined login或storage token。
3. 使用明確標記的disposable `lu_test_*`資料庫與synthetic ticket／binding；若環境或受控資料不存在，狀態為
   `BLOCKED_CONTROLLED_RUNTIME_INPUT`，不得對既有`union_db`或真人LINE身分操作。
4. LINE provider、worker delivery與wakeup均替換為受控test adapter；驗證0真人訊息／0 provider call。
5. Query至少證明success、empty、401、403、typed error、timeout／abort／stale；兩mutation證明Preview零寫入、
   Apply single-flight、server reject、receipt、re-query observed、outcome_unknown同key replay。
6. Identity Apply只可顯示accepted；只有re-query binding/root fact能顯示revoked。客服Resolve同樣以re-query observed
   為成功，不以HTTP 200或Apply payload冒充完成。
7. Browser receipt逐request記錄去敏method/path/status/correlation/idempotency/receipt identity與對應DOM stable ID；
   截圖、unit test或空頁不可替代Network↔DOM證據。
8. Fresh執行Phase 3A focused frontend/backend suites、全React build/lint/test、strict UTF-8、secret/PII與
   `git diff --check`。任何skip、unexpected network、provider call或production drift均fail closed。
9. 只有全部PASS才可把原Phase 3A工作包從`blocked`更新為`completed-local-validated`並連結本closure receipt；
   closure本身完成不代表Phase 5 entry可切換，仍需Phase4 query、Auth normalization、Phase5A/5B。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | BLOCKED | 等待exact核准與受控runtime input |
| Change Inventory | PASS | 0 schema／seed／backfill／destructive；只允許disposable runtime rows |
| Static Release | NOT_RUN | 無schema change |
| Descriptor | NOT_RUN | 無schema change |
| Read-only Plan | NOT_RUN | 無migration |
| Engine Verification | NOT_RUN | 核准後只用disposable MySQL |
| Developer Acceptance | NOT_RUN | 禁止既有DB與真人LINE |

結論：`DB_CHANGE_NOT_READY`。

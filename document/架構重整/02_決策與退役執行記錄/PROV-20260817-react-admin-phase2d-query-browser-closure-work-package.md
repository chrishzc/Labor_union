---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase2d-query-browser-closure
date: 2026-08-17
owner: Anomalies Query Closure Integration Owner
domain: Anomalies / Import Warning Tracking
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment PASS
candidate_baseline_required: PROV-20260816-react-admin-phase2d-anomalies-query implementation present; fresh base-drift audit required
approval_required: 核准此 exact Phase 2D Query Browser Closure Work Package
ui_execution_mode: controlled-browser-required
production_write_set: none
db_schema_write_set: none
successors: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment
---

# Phase 2D Anomalies／Import Warning Query Browser Closure 工作包

## Supersession record（2026-08-17）

本提案從未取得exact施工核准；其唯一browser目的已由已核准的Phase 2D-H Closure Amendment及同一
evidence目錄中的`browser-smoke-receipt.md`、`closure-gate-verification-receipt.md`完成。為避免兩個
競爭closure owner，本文件標為`superseded`，不得偽稱本提案曾執行或完成。

## 0. Purpose

只重驗既有Phase 2D兩條核准GET與Anomalies頁面的真實兩段式登入、Network↔DOM、empty／error／pagination
行為，解開舊Query工作包的browser evidence blocker。此包不啟用Claim、Resolve、Warning transition、repair或
任何non-GET，也不修改production。

## 1. Exact write set

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2d-anomalies-query-work-package.md`（只有全部gate PASS時更新status/evidence）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase2d-query-browser-closure/candidate-change-inventory.md`（new）
- 同目錄`verification-receipt.md`、`browser-smoke-receipt.md`、`open-findings.md`（new）
- 本工作包與`02_決策與退役執行記錄/README.md`（Integration Owner only）

禁止修改production、tests、validation、DB/schema、entry queue或launcher。若現行decoder、adapter或page仍有缺陷，
輸出`BLOCKED_PRODUCTION_SUCCESSOR_REQUIRED`並建立另案，不可在closure包偷偷修碼。

## 2. Acceptance

1. 真FastAPI＋Vite、password challenge→TOTP→memory session；禁止dev token／storage token。
2. 只允許`GET /api/v1/anomalies?include_snapshot=false`與
   `GET /api/v1/import-warning-tracking/tasks`及既有System/Auth GET；所有unexpected non-GET立即fail。
3. 使用去敏controlled query data；證明success、empty、cursor／loaded-scope、401、403、typed schema failure、
   timeout、abort、stale discard與retry。KPI明示loaded scope，不把當頁計數冒充全域總數。
4. 每一READY_TYPED server field至少有兩組sentinel response→不同DOM assertion；BACKEND_GAP槽位仍明示
   unavailable，不能以硬編摘要或全空頁通過。
5. Browser receipt逐request記錄去敏method/path/status/correlation與對應DOM stable ID；截圖、Happy-DOM或
   HTTP 200不能單獨構成PASS。
6. Fresh跑Phase 2D focused frontend/backend suites、全React build/lint/test、strict UTF-8、secret/PII、
   non-GET與`git diff --check`；closure前後production bytes完全一致。
7. 全部PASS才可把原Phase 2D Query工作包更新為`completed-local-validated`並連結本receipt；Warning／detail／
   Claim／Resolve gates維持各自獨立。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | BLOCKED | 等待exact核准與controlled query data |
| Change Inventory | PASS | query-only；0 schema／seed／backfill／destructive |
| Static Release | NOT_RUN | 無schema change |
| Descriptor | NOT_RUN | 無schema change |
| Read-only Plan | NOT_RUN | 無migration |
| Engine Verification | NOT_RUN | 本closure不寫DB |
| Developer Acceptance | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

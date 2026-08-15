---
doc_type: work-package
declared_status: superseded
date: 2026-08-15
owner: Global schema / Scheduling / Payroll / Orders / Runtime / Staff
priority: P0
---

# PROV-20260815 Schema baseline drift recovery

## Superseded finding (2026-08-15)

此 recovery package 不授權施工。原先的 `partial/drift` 結果來自直接呼叫低階 migration CLI 卻未提供
canonical release manifest chain；重新以完整 selection 的 read-only snapshot 驗證後，107、109、112、116、161
與 193 均為 `exact`。後續 WP91 candidate 驗證必須使用載入完整 chain 的 runner path，不得將此假陽性
當作 source schema defect。

## Business scenario

開發者本機的保留資料 schema upgrade 必須在不改動來源資料的情況下，建立可驗證的 candidate。任何既有
owned object 為 `partial` 或 `drift` 時，後續 release 必須 fail closed，而不是跳過驗證或把 WP91
Staff retirement schema 直接套入不完整 baseline。

## Evidence

Docker `mysql_db` 的 isolated candidate rehearsal 已建立 source backup 並還原 candidate，隨後在 schema
apply 前停在下列 source owned-object states：

| Artifact | State | Owning boundary |
|---|---|---|
| `107_system_alert_current_projection.sql` | `drift` | Global runtime alert projection |
| `109_scheduling_generations.sql` | `partial` | Scheduling generation |
| `112_payroll_obligations.sql` | `partial` | Payroll obligation |
| `116_order_actual_start_workflow.sql` | `partial` | Orders actual start |
| `161_runtime_monitoring_line_alerts.sql` | `partial` | Runtime monitoring |
| `193_staff_historical_adoption_hcm_review.sql` | `partial` | Staff historical adoption |

## Proposed scope

- 對每個 artifact 取得 source `absent/exact/partial/drift` 的欄位、index、FK、check、trigger、view 差異。
- 只以新的 additive successor artifacts 修復可安全補齊的 metadata；不改已發布 SQL、release manifest、descriptor bytes 或 release identity。
- 每個可能涉及既有列資料的 repair 必須另外分類為 `business-row-backfill`，具 dry-run、影響筆數、unresolved review、replay 與 rollback evidence。
- 在 disposable source → candidate 重新驗證所有六個 owner 及 WP91 `1000_staff_retirement.sql`。

## Non-goals

- 不替換、重建或直接修改 configured source／`union_db`。
- 不把 source partial/drift 視為可忽略，也不以 mock 取代 MySQL evidence。
- 不改變 Staff retirement 的 owner、SSOT、business policy 或 release identity。

## DB change gate

| gate | status | Evidence / next action |
|---|---|---|
| Scope gate | `PASS` | 已人工確認先做 impact analysis；結果證實此 package 是 false-positive，不進行 schema repair |
| Change inventory | `NOT_RUN` | 需逐一盤點六個 artifact 的 metadata 與資料效果 |
| Static release gate | `NOT_RUN` | 尚未建立 successor artifacts |
| Descriptor gate | `NOT_RUN` | 尚未取得 exact differences |
| Read-only plan gate | `PASS` | Docker `mysql_db` 可解析 full chain 與 WP91 release |
| Engine verification gate | `NOT_RUN` | 必須改用完整 canonical release chain 的 candidate-only apply |
| Developer acceptance gate | `NOT_RUN` | 不得操作既有 source |

總結：`DB_CHANGE_NOT_READY`。

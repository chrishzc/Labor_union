---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-government-subsidy-reporting-authority-decision
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Government Subsidy / Reporting Integration Owner
domain: Government Subsidy / Reporting
source_gap: PROV-20260817-government-subsidy-reporting-authority-gap
approval_required: 核准此 exact Government Subsidy Reporting Authority Decision Work Package
ui_execution_mode: not-applicable
prerequisites: none (docs-only authority decision)
---

# Government Subsidy reporting authority decision 工作包

## Scope／write set

只建立逐欄authority matrix，不改production：

- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- source gap、Phase 4B-S blocked WP、本工作包與`02/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-government-subsidy-reporting-authority-gap/report-field-authority-matrix.md`（new）

0 route/query/repository/test fixture/React/XLSX/DB。Integration Owner是唯一writer。

## Protocol／acceptance

1. Scout只列live field/SQL/formula與正式規格差異，不以live結果作裁決。
2. 每欄人工選定canonical owner/root fact、公式、period/timezone、nullable、lineage/version、
   DISPLAY／EXPORT_ONLY／REDACTED、aggregate conservation、empty semantics與禁止推導來源。
3. 無法由approved spec唯一決定者維持`DECISION_REQUIRED`；整包不得completed，4B-S維持blocked。
4. Scenario映射P00-G47／G48／G54；不得用ReportsPage、Streamlit、fixture或HTTP 200自證expected。
5. 矩陣無未決欄位後，只解除4B-S重新申請exact production approval，不直接授權實作。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | docs/evidence only |
| Change inventory | PASS | schema/seed/backfill/destructive皆none |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無DB object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

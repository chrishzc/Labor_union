---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-case-import-workbook-policy-decision
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Case Import Integration Owner
domain: Case Import / Staff / Orders Historical Adoption
source_gaps: PROV-20260817-case-import-workbook-atomicity-archive-policy-gap; PROV-20260817-hcm-workbook-source-archive-decision-gap
approval_required: 核准此 exact Case Import Workbook Policy Decision Work Package，並採用本文推薦值
ui_execution_mode: not-applicable
prerequisites: none (docs-only policy decision)
authority: exact-human-approved-2026-08-23
decision_outcome: recommended-values-adopted
---

# Case Import workbook policy decision 工作包

## 人工裁決（2026-08-23）

人工已exact核准本文推薦值：HCM identity duplicate採`review_only`；HCM Current採
`WHOLE_WORKBOOK + archive_required`；Client BeClass、Staff Historical、Historical Orders各採
`ROW_ATOMIC_RESUMABLE + archive_required`。本裁決只凍結規格，不授權production writer、schema／DB、
React Apply、entry switch或production host。

## 0. 推薦裁決值

- HCM exact IP＋normalized name命中既有Client：`review_only`，不得同時建立partial case。
- HCM Current：`WHOLE_WORKBOOK`＋`archive_required`（Source Archive Option A）。
- Client BeClass：`ROW_ATOMIC_RESUMABLE`＋`archive_required`。
- Staff Historical：`ROW_ATOMIC_RESUMABLE`＋`archive_required`。
- Historical Orders：`ROW_ATOMIC_RESUMABLE`＋`archive_required`。

此推薦優先保護日常HCM匯入的一致性；三種歷史採用則允許大量資料在明確row receipt下續跑。若static
inventory證明既有tables不能表達running/progress/archive recovery，本包只輸出`DB_SCOPE_REQUIRED`，不改DB。

## 1. Exact write set

- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/01_Orders_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-case-import-workbook-atomicity-archive-policy-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-hcm-workbook-source-archive-decision-gap.md`
- 本工作包與`02/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-case-import-workbook-atomicity-archive-policy-gap/workbook-family-decision-matrix.md`（new）

0 production code/test/validation fixture/DB。所有檔案只由Integration Owner寫入；Scout只能回傳source evidence。

## 2. Execution protocol

1. Luna唯讀列出四family現行claim/receipt/archive/commit paths與表達能力，不得裁決。
2. Terra唯讀將本文推薦值投影成逐family state/replay/stale/archive矩陣，不得改production。
3. Primary以正式規格核對owner/root fact，處理衝突並freeze唯一matrix。
4. Integration Owner一次更新正式規格、gap、index與receipt；不得把live code行為升格為authority。

## 3. Acceptance

- 四family每一列都具source identity、fingerprint inputs、target expected versions、atomicity、terminal disposition、
  PII class、archive/recovery、receipt selector、replay/stale/conflict與warning/outbox owner。
- `ROW_ATOMIC_RESUMABLE`具running/row receipt/terminal aggregate/recovery語意；缺持久能力時明列DB successor，
  不用log或temp file補洞。
- HCM identity conflict只有一個正式結果；不得同時允許review-only與partial case。
- Route A/B scenario identity與後續exact backend WP連結完整。
- strict UTF-8、`git diff --check`、inbound link與狀態一致性通過。
- 採用本文Option A時，Integration Owner在同一decision receipt中把HCM專屬archive gap標為`superseded`，
  successor指向本combined decision；不得保留兩個active Source Archive SSOT。若人工未採Option A，兩gap都保持blocked。

## 4. Completion boundary

完成只代表policy decision complete；不授權4A-H/CW-H production writer。後續仍需分別exact核准。

## 5. DB gate

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

## 6. Completion receipt

- canonical matrix：`../03_追蹤清單與證據/evidence/PROV-20260817-case-import-workbook-atomicity-archive-policy-gap/workbook-family-decision-matrix.md`
- 正式規格已同步`01_Orders_Domain.md`、`17_External_Integration_LINE_Access正式規格.md`與
  `15_正式規格索引與裁決總表.md`。
- combined atomicity/archive gap與HCM專屬archive gap已由本decision supersede。
- static inventory顯示現有claim／terminal receipt不足以表達四family所需archive與完整
  running/progress/recovery，因此production successor固定輸出`DB_SCOPE_REQUIRED`；未執行DDL、migration或DB。

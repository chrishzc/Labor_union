---
doc_type: gap
declared_status: proposed
identity: PROV-20260817-government-subsidy-reporting-authority-gap
date: 2026-08-17
owner: Government Subsidy / Reporting Integration Owner
domain: Government Subsidy / Reporting
approval_required: 人工裁決補助報表root facts、公式、期間與公開欄位權威
---

# Government Subsidy reporting authority gap

## Gap

現行quarterly／annual reconciliation query直接組合legacy MySQL欄位、rate與跨表公式；route可運作不代表
這些公式已成為Government Subsidy正式root fact或Reporting authority。未經裁決，不能以既有fixture或
Streamlit結果自證typed public contract，更不能核准React報表接線。

## 人工裁決矩陣

每一欄必須列出canonical owner/root fact、公式、期間與時區、nullable、lineage/version、DISPLAY／
EXPORT_ONLY／REDACTED、aggregate conservation、empty semantics與禁止推導來源。未能由正式規格唯一決定者
維持`DECISION_REQUIRED`；不得由live SQL、hard-coded rate或UI樣本補值。

## Exact gap write set

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-government-subsidy-reporting-authority-gap/report-field-authority-matrix.md`（new）
- 本gap、`02/README.md`、`14_Government_Subsidy_Domain.md`與`15_正式規格索引與裁決總表.md`
  只由Integration Owner更新。

## Out of scope

0 production route/query/repository、0 React、0 XLSX、0 DB/schema。矩陣無未決欄位後，才可重新核准
Phase 4B-S public contract hardening；generic weekly workbook仍屬獨立gap。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | root facts／公式authority未決 |
| Change inventory | NOT_RUN | 文件裁決前無production scope |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無DB object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
